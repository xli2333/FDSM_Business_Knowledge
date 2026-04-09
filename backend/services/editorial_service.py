from __future__ import annotations

import hashlib
import html
import io
import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from backend.config import COLUMN_DEFINITIONS
from backend.database import connection_scope, ensure_runtime_tables
from backend.services.article_ai_output_service import (
    get_article_ai_output_detail,
    list_article_ai_source_articles,
)
from backend.services import ai_service
from backend.services.html_renderer import render_editorial_package, strip_markdown
from backend.services.membership_service import access_level_label, normalize_access_level
from backend.services.rag_engine import refresh_search_cache
from backend.services.tag_engine import _derive_tag_entries, _ensure_tag
from backend.scripts.build_business_db import COLOR_BY_CATEGORY, slugify

ensure_runtime_tables()

VALID_COLUMN_SLUGS = {item["slug"] for item in COLUMN_DEFINITIONS}
TAG_PRIORITY = {"industry": 0, "topic": 1, "type": 2, "entity": 3, "series": 4}
WORKFLOW_LABELS = {
    "draft": "草稿",
    "in_review": "待审核",
    "approved": "已通过",
    "scheduled": "定时发布",
    "published": "已发布",
}
LAYOUT_MODE_LABELS = {
    "auto": "自动排版",
    "insight": "深度长文",
    "briefing": "快报简版",
    "interview": "访谈实录",
}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _normalize_publish_date(value: str | None) -> str:
    if not value:
        return date.today().isoformat()
    text = value.strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return date.today().isoformat()


def workflow_status_label(value: str | None) -> str:
    return WORKFLOW_LABELS.get((value or "").strip() or "draft", "草稿")


def _normalize_workflow_status(value: str | None) -> str:
    workflow_status = (value or "").strip() or "draft"
    if workflow_status not in WORKFLOW_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported workflow status")
    return workflow_status


def _normalize_schedule_datetime(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).replace(microsecond=0).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid scheduled publish time") from exc


def _normalize_layout_mode(value: str | None) -> str:
    layout_mode = (value or "").strip() or "auto"
    if layout_mode not in LAYOUT_MODE_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported layout mode")
    return layout_mode


def _extract_excerpt(text: str, limit: int = 140) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def _word_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _load_tag_payload(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _serialize_editorial_row(row) -> dict:
    return {
        "id": row["id"],
        "article_id": row["article_id"],
        "source_article_id": row["source_article_id"] if "source_article_id" in row.keys() else None,
        "slug": row["slug"],
        "title": row["title"],
        "subtitle": row["subtitle"],
        "author": row["author"],
        "organization": row["organization"],
        "publish_date": row["publish_date"],
        "source_url": row["source_url"],
        "cover_image_url": row["cover_image_url"],
        "primary_column_slug": row["primary_column_slug"],
        "article_type": row["article_type"],
        "main_topic": row["main_topic"],
        "access_level": row["access_level"] or "public",
        "access_label": access_level_label(row["access_level"] or "public"),
        "workflow_status": _normalize_workflow_status(row["workflow_status"]),
        "workflow_label": workflow_status_label(row["workflow_status"]),
        "review_note": row["review_note"],
        "scheduled_publish_at": row["scheduled_publish_at"],
        "submitted_at": row["submitted_at"],
        "approved_at": row["approved_at"],
        "ai_synced_at": row["ai_synced_at"] if "ai_synced_at" in row.keys() else None,
        "layout_mode": row["layout_mode"] if "layout_mode" in row.keys() and row["layout_mode"] else "auto",
        "formatting_notes": row["formatting_notes"] if "formatting_notes" in row.keys() else None,
        "formatter_model": row["formatter_model"] if "formatter_model" in row.keys() else None,
        "last_formatted_at": row["last_formatted_at"] if "last_formatted_at" in row.keys() else None,
        "source_markdown": row["source_markdown"] if "source_markdown" in row.keys() and row["source_markdown"] else row["content_markdown"],
        "content_markdown": row["content_markdown"],
        "plain_text_content": row["plain_text_content"],
        "excerpt": row["excerpt"],
        "tags": _load_tag_payload(row["tag_payload_json"]),
        "html_web": row["html_web"],
        "html_wechat": row["html_wechat"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "published_at": row["published_at"],
    }


def _fetch_editorial_row(connection, editorial_id: int):
    row = connection.execute(
        """
        SELECT *
        FROM editorial_articles
        WHERE id = ?
        """,
        (editorial_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Editorial article not found")
    return row


def _unique_slug(connection, table: str, base_slug: str, *, exclude_id: int | None = None) -> str:
    candidate = base_slug or f"draft-{date.today().isoformat()}"
    suffix = 1
    while True:
        row = connection.execute(f"SELECT id FROM {table} WHERE slug = ?", (candidate,)).fetchone()
        if row is None or (exclude_id is not None and row["id"] == exclude_id):
            return candidate
        digest = hashlib.sha1(f"{base_slug}:{suffix}".encode("utf-8")).hexdigest()[:6]
        candidate = f"{base_slug[:70]}-{digest}"
        suffix += 1


def _dedupe_tags(entries: list[tuple[str, str, float]]) -> list[dict]:
    merged: dict[tuple[str, str], float] = {}
    for raw_name, category, confidence in entries:
        name = raw_name.strip()
        if not name:
            continue
        safe_category = category if category in TAG_PRIORITY else "topic"
        key = (name, safe_category)
        merged[key] = max(float(confidence), merged.get(key, 0.0))

    payload = [
        {
            "name": name,
            "slug": slugify(f"{category}-{name}")[:80],
            "category": category,
            "color": COLOR_BY_CATEGORY.get(category, "#64748b"),
            "confidence": round(confidence, 3),
        }
        for (name, category), confidence in merged.items()
    ]
    payload.sort(key=lambda item: (TAG_PRIORITY.get(item["category"], 9), -item["confidence"], item["name"]))
    return payload[:12]


def _infer_column_slug(article: dict, tags: list[dict]) -> str:
    haystack = " ".join(
        [
            article.get("title") or "",
            article.get("article_type") or "",
            article.get("main_topic") or "",
            article.get("organization") or "",
            " ".join(tag["name"] for tag in tags),
        ]
    )
    if any(token in haystack for token in ("研究", "论文", "学术", "案例教学")):
        return "research"
    if any(token in haystack for token in ("院长", "教授", "复旦", "管理学院")):
        return "deans-view"
    if any(tag.get("category") == "industry" for tag in tags):
        return "industry"
    return "insights"


def _decode_text_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _html_to_markdown_like(content: str) -> str:
    text = content.replace("\r\n", "\n")
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*/p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<\s*h1[^>]*>(.*?)<\s*/h1\s*>", lambda m: f"# {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n\n", text, flags=re.I | re.S)
    text = re.sub(r"<\s*h2[^>]*>(.*?)<\s*/h2\s*>", lambda m: f"## {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n\n", text, flags=re.I | re.S)
    text = re.sub(r"<\s*h3[^>]*>(.*?)<\s*/h3\s*>", lambda m: f"### {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n\n", text, flags=re.I | re.S)
    text = re.sub(r"<\s*li[^>]*>(.*?)<\s*/li\s*>", lambda m: f"- {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n", text, flags=re.I | re.S)
    text = re.sub(r"<\s*(strong|b)[^>]*>(.*?)<\s*/\1\s*>", lambda m: f"**{re.sub(r'<[^>]+>', '', m.group(2)).strip()}**", text, flags=re.I | re.S)
    text = re.sub(r"<\s*(em|i)[^>]*>(.*?)<\s*/\1\s*>", lambda m: f"*{re.sub(r'<[^>]+>', '', m.group(2)).strip()}*", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _docx_to_markdown_like(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise HTTPException(status_code=400, detail="DOCX document.xml is missing") from exc

    root = ET.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        style_value = ""
        style = paragraph.find("./w:pPr/w:pStyle", namespace)
        if style is not None:
            style_value = str(style.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") or "")
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if not text:
            continue
        if style_value.startswith("Heading1"):
            paragraphs.append(f"# {text}")
        elif style_value.startswith("Heading2"):
            paragraphs.append(f"## {text}")
        elif style_value.startswith("Heading3"):
            paragraphs.append(f"### {text}")
        else:
            paragraphs.append(text)
    return "\n\n".join(paragraphs).strip()


def _extract_upload_content(filename: str, raw_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return _docx_to_markdown_like(raw_bytes)
    content = _decode_text_bytes(raw_bytes)
    normalized = content.replace("\r\n", "\n").strip()
    if suffix in {".html", ".htm"}:
        return _html_to_markdown_like(normalized)
    return normalized


def list_editorial_articles(
    limit: int = 40,
    status: str | None = None,
    workflow_status: str | None = None,
) -> list[dict]:
    safe_limit = max(1, min(limit, 100))
    query = """
        SELECT *
        FROM editorial_articles
        {where_sql}
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
    """
    params: list[object] = []
    filters: list[str] = []
    if status:
        filters.append("status = ?")
        params.append(status)
    if workflow_status:
        filters.append("workflow_status = ?")
        params.append(_normalize_workflow_status(workflow_status))
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connection_scope() as connection:
        rows = connection.execute(query.format(where_sql=where_sql), (*params, safe_limit)).fetchall()
    return [_serialize_editorial_row(row) for row in rows]


def get_editorial_article(editorial_id: int) -> dict:
    with connection_scope() as connection:
        row = _fetch_editorial_row(connection, editorial_id)
    payload = _serialize_editorial_row(row)
    if payload.get("source_article_id"):
        payload["source_article_ai"] = get_article_ai_output_detail(int(payload["source_article_id"]))
    else:
        payload["source_article_ai"] = None
    return payload


def get_editorial_dashboard(limit: int = 6) -> dict:
    safe_limit = max(1, min(limit, 12))
    with connection_scope() as connection:
        workflow_rows = connection.execute(
            """
            SELECT workflow_status, COUNT(*) AS total
            FROM editorial_articles
            GROUP BY workflow_status
            """
        ).fetchall()
        workflow_map = {
            _normalize_workflow_status(row["workflow_status"]): int(row["total"])
            for row in workflow_rows
        }
        latest_row = connection.execute(
            """
            SELECT published_at, article_id
            FROM editorial_articles
            WHERE status = 'published'
            ORDER BY published_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        export_ready_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM editorial_articles
            WHERE html_web IS NOT NULL AND html_wechat IS NOT NULL
            """
        ).fetchone()[0]
        recent_rows = connection.execute(
            """
            SELECT *
            FROM editorial_articles
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return {
        "draft_count": workflow_map.get("draft", 0),
        "published_count": workflow_map.get("published", 0),
        "pending_review_count": workflow_map.get("in_review", 0),
        "approved_count": workflow_map.get("approved", 0),
        "scheduled_count": workflow_map.get("scheduled", 0),
        "latest_published_at": latest_row["published_at"] if latest_row else None,
        "latest_article_id": latest_row["article_id"] if latest_row else None,
        "export_ready_count": export_ready_count,
        "workflow_counts": [
            {
                "workflow_status": key,
                "workflow_label": workflow_status_label(key),
                "total": workflow_map.get(key, 0),
            }
            for key in ("draft", "in_review", "approved", "scheduled", "published")
        ],
        "recent_items": [_serialize_editorial_row(row) for row in recent_rows],
    }


def _fetch_source_article_row(connection, article_id: int) -> dict:
    row = connection.execute(
        """
        SELECT
            id,
            slug,
            title,
            publish_date,
            link,
            excerpt,
            main_topic,
            article_type,
            primary_org_name,
            access_level,
            content
        FROM articles
        WHERE id = ?
        """,
        (article_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Source article not found")
    return dict(row)


def _fetch_source_article_tags(connection, article_id: int) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            t.name,
            t.slug,
            t.category,
            t.color,
            at.confidence
        FROM article_tags at
        JOIN tags t ON t.id = at.tag_id
        WHERE at.article_id = ?
        ORDER BY at.confidence DESC, t.article_count DESC, t.name ASC
        LIMIT 12
        """,
        (article_id,),
    ).fetchall()
    return [
        {
            "name": row["name"],
            "slug": row["slug"],
            "category": row["category"],
            "color": row["color"],
            "confidence": round(float(row["confidence"] or 0.7), 3),
        }
        for row in rows
    ]


def _fetch_source_article_column_slug(connection, article_id: int) -> str | None:
    row = connection.execute(
        """
        SELECT c.slug
        FROM article_columns ac
        JOIN columns c ON c.id = ac.column_id
        WHERE ac.article_id = ?
        ORDER BY ac.is_featured DESC, ac.sort_order ASC, c.sort_order ASC, c.name ASC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()
    return row["slug"] if row is not None else None


def list_editorial_source_articles(query: str = "", limit: int = 12) -> list[dict]:
    return list_article_ai_source_articles(query=query, limit=limit)


def get_editorial_source_ai_output(article_id: int) -> dict:
    return get_article_ai_output_detail(article_id)


def import_editorial_ai_draft(source_article_id: int, payload: dict | None = None) -> dict:
    request_payload = payload or {}
    editorial_id = request_payload.get("editorial_id")
    ai_output = get_article_ai_output_detail(source_article_id)
    formatted_markdown = str(ai_output.get("formatted_markdown_zh") or "").strip()
    if not ai_output.get("format_ready") or not formatted_markdown:
        raise HTTPException(status_code=400, detail="AI formatted Chinese draft is not ready for this article")

    now = _now_iso()
    with connection_scope() as connection:
        source_row = _fetch_source_article_row(connection, source_article_id)
        tag_payload = _fetch_source_article_tags(connection, source_article_id)
        column_slug = _fetch_source_article_column_slug(connection, source_article_id) or "insights"
        plain_text_content = strip_markdown(formatted_markdown)
        summary_excerpt = strip_markdown(str(ai_output.get("summary_zh") or "")).strip()
        excerpt = (
            _extract_excerpt(summary_excerpt, limit=180)
            if summary_excerpt
            else source_row.get("excerpt") or _extract_excerpt(plain_text_content)
        )
        source_markdown = str(source_row.get("content") or formatted_markdown).strip()
        access_level = normalize_access_level(source_row.get("access_level"))
        organization = source_row.get("primary_org_name") or "Fudan Business Knowledge"
        author = "Fudan Business Knowledge Editorial Desk"

        if editorial_id:
            current = dict(_fetch_editorial_row(connection, int(editorial_id)))
            if current["status"] == "published":
                raise HTTPException(
                    status_code=400,
                    detail="Published editorial article cannot be overwritten from AI import",
                )
            if current.get("author"):
                author = current["author"]
            if current.get("organization"):
                organization = current["organization"]
            desired_slug = slugify((current.get("slug") or source_row.get("slug") or source_row["title"]).strip())[:80]
            unique_slug = _unique_slug(connection, "editorial_articles", desired_slug, exclude_id=int(editorial_id))
            connection.execute(
                """
                UPDATE editorial_articles
                SET source_article_id = ?,
                    slug = ?,
                    title = ?,
                    author = ?,
                    organization = ?,
                    publish_date = ?,
                    source_url = ?,
                    primary_column_slug = ?,
                    article_type = ?,
                    main_topic = ?,
                    access_level = ?,
                    source_markdown = ?,
                    layout_mode = ?,
                    formatting_notes = NULL,
                    formatter_model = ?,
                    last_formatted_at = ?,
                    content_markdown = ?,
                    plain_text_content = ?,
                    excerpt = ?,
                    tag_payload_json = ?,
                    html_web = NULL,
                    html_wechat = NULL,
                    ai_synced_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    source_article_id,
                    unique_slug,
                    source_row["title"],
                    author,
                    organization,
                    _normalize_publish_date(source_row.get("publish_date")),
                    source_row.get("link"),
                    column_slug,
                    source_row.get("article_type"),
                    source_row.get("main_topic"),
                    access_level,
                    source_markdown,
                    "auto",
                    str(ai_output.get("format_model") or ""),
                    now,
                    formatted_markdown,
                    plain_text_content,
                    excerpt,
                    json.dumps(tag_payload, ensure_ascii=False),
                    now,
                    now,
                    int(editorial_id),
                ),
            )
            connection.commit()
            return get_editorial_article(int(editorial_id))

        desired_slug = slugify((source_row.get("slug") or source_row["title"]).strip())[:80]
        unique_slug = _unique_slug(connection, "editorial_articles", desired_slug)
        connection.execute(
            """
            INSERT INTO editorial_articles (
                article_id,
                source_article_id,
                slug,
                title,
                subtitle,
                author,
                organization,
                publish_date,
                source_url,
                cover_image_url,
                primary_column_slug,
                article_type,
                main_topic,
                access_level,
                source_markdown,
                layout_mode,
                formatting_notes,
                formatter_model,
                last_formatted_at,
                content_markdown,
                plain_text_content,
                excerpt,
                tag_payload_json,
                html_web,
                html_wechat,
                status,
                workflow_status,
                ai_synced_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL, 'draft', 'draft', ?, ?, ?)
            """,
            (
                None,
                source_article_id,
                unique_slug,
                source_row["title"],
                author,
                organization,
                _normalize_publish_date(source_row.get("publish_date")),
                source_row.get("link"),
                column_slug,
                source_row.get("article_type"),
                source_row.get("main_topic"),
                access_level,
                source_markdown,
                "auto",
                str(ai_output.get("format_model") or ""),
                now,
                formatted_markdown,
                plain_text_content,
                excerpt,
                json.dumps(tag_payload, ensure_ascii=False),
                now,
                now,
                now,
            ),
        )
        editorial_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.commit()
    return get_editorial_article(editorial_id)


def create_editorial_article(payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    content_markdown = str(payload.get("content_markdown") or "").strip()
    source_markdown = str(payload.get("source_markdown") or "").strip()
    if not content_markdown and source_markdown:
        content_markdown = source_markdown
    if not source_markdown and content_markdown:
        source_markdown = content_markdown
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if not content_markdown:
        raise HTTPException(status_code=400, detail="Content is required")

    now = _now_iso()
    plain_text_content = strip_markdown(content_markdown)
    excerpt = _extract_excerpt(plain_text_content)
    access_level = normalize_access_level(payload.get("access_level"))
    layout_mode = _normalize_layout_mode(payload.get("layout_mode"))
    formatting_notes = str(payload.get("formatting_notes") or "").strip() or None

    with connection_scope() as connection:
        desired_slug = slugify((payload.get("slug") or title).strip())[:80]
        unique_slug = _unique_slug(connection, "editorial_articles", desired_slug)
        connection.execute(
            """
            INSERT INTO editorial_articles (
                slug, title, subtitle, author, organization, publish_date, source_url,
                cover_image_url, primary_column_slug, article_type, main_topic, access_level,
                source_markdown, layout_mode, formatting_notes, content_markdown, plain_text_content, excerpt, tag_payload_json,
                html_web, html_wechat, status, workflow_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', NULL, NULL, 'draft', 'draft', ?, ?)
            """,
            (
                unique_slug,
                title,
                payload.get("subtitle"),
                payload.get("author"),
                payload.get("organization"),
                _normalize_publish_date(payload.get("publish_date")),
                payload.get("source_url"),
                payload.get("cover_image_url"),
                payload.get("primary_column_slug"),
                payload.get("article_type"),
                payload.get("main_topic"),
                access_level,
                source_markdown,
                layout_mode,
                formatting_notes,
                content_markdown,
                plain_text_content,
                excerpt,
                now,
                now,
            ),
        )
        editorial_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.commit()
    return get_editorial_article(int(editorial_id))


def update_editorial_article(editorial_id: int, payload: dict) -> dict:
    allowed_fields = {
        "title",
        "subtitle",
        "author",
        "organization",
        "publish_date",
        "source_url",
        "cover_image_url",
        "primary_column_slug",
        "article_type",
        "main_topic",
        "access_level",
        "source_markdown",
        "layout_mode",
        "formatting_notes",
        "content_markdown",
    }
    updates = {key: value for key, value in payload.items() if key in allowed_fields and value is not None}
    if not updates and payload.get("slug") is None:
        return get_editorial_article(editorial_id)

    with connection_scope() as connection:
        current = dict(_fetch_editorial_row(connection, editorial_id))
        if "title" in updates and not str(updates["title"]).strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        if "content_markdown" in updates and not str(updates["content_markdown"]).strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        if "source_markdown" in updates and not str(updates["source_markdown"]).strip():
            raise HTTPException(status_code=400, detail="Source content cannot be empty")

        desired_slug = payload.get("slug")
        if desired_slug is not None:
            normalized_slug = slugify(str(desired_slug).strip())[:80]
            current["slug"] = _unique_slug(connection, "editorial_articles", normalized_slug, exclude_id=editorial_id)
        elif "title" in updates:
            current["slug"] = current["slug"]

        for key, value in updates.items():
            current[key] = value

        current["publish_date"] = _normalize_publish_date(current.get("publish_date"))
        current["access_level"] = normalize_access_level(current.get("access_level"))
        current["layout_mode"] = _normalize_layout_mode(current.get("layout_mode"))
        current["source_markdown"] = str(current.get("source_markdown") or current.get("content_markdown") or "").strip()
        current["plain_text_content"] = strip_markdown(current.get("content_markdown") or "")
        current["excerpt"] = _extract_excerpt(current["plain_text_content"])
        current["updated_at"] = _now_iso()
        if current.get("formatting_notes") is not None:
            current["formatting_notes"] = str(current.get("formatting_notes") or "").strip() or None

        connection.execute(
            """
            UPDATE editorial_articles
            SET slug = ?, title = ?, subtitle = ?, author = ?, organization = ?, publish_date = ?,
                source_url = ?, cover_image_url = ?, primary_column_slug = ?, article_type = ?,
                main_topic = ?, access_level = ?, source_markdown = ?, layout_mode = ?, formatting_notes = ?,
                content_markdown = ?, plain_text_content = ?, excerpt = ?,
                html_web = NULL, html_wechat = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                current["slug"],
                current["title"],
                current.get("subtitle"),
                current.get("author"),
                current.get("organization"),
                current["publish_date"],
                current.get("source_url"),
                current.get("cover_image_url"),
                current.get("primary_column_slug"),
                current.get("article_type"),
                current.get("main_topic"),
                current["access_level"],
                current["source_markdown"],
                current["layout_mode"],
                current.get("formatting_notes"),
                current.get("content_markdown"),
                current["plain_text_content"],
                current["excerpt"],
                current["updated_at"],
                editorial_id,
            ),
        )
        connection.commit()
    return get_editorial_article(editorial_id)


def update_editorial_workflow(editorial_id: int, payload: dict) -> dict:
    action = (payload.get("action") or "").strip()
    if action not in {"save_draft", "submit_review", "approve", "schedule"}:
        raise HTTPException(status_code=400, detail="Unsupported workflow action")

    timestamp = _now_iso()
    review_note = payload.get("review_note")
    scheduled_publish_at = _normalize_schedule_datetime(payload.get("scheduled_publish_at"))

    with connection_scope() as connection:
        current = dict(_fetch_editorial_row(connection, editorial_id))
        if current["status"] == "published":
            raise HTTPException(status_code=400, detail="Published article workflow is locked")

        next_workflow_status = "draft"
        next_review_note = review_note if review_note is not None else current.get("review_note")
        next_scheduled_publish_at = current.get("scheduled_publish_at")
        next_submitted_at = current.get("submitted_at")
        next_approved_at = current.get("approved_at")

        if action == "save_draft":
            next_workflow_status = "draft"
            next_scheduled_publish_at = None
        elif action == "submit_review":
            next_workflow_status = "in_review"
            next_submitted_at = timestamp
            next_scheduled_publish_at = None
        elif action == "approve":
            next_workflow_status = "approved"
            next_approved_at = timestamp
        elif action == "schedule":
            if not scheduled_publish_at:
                raise HTTPException(status_code=400, detail="Scheduled publish time is required")
            next_workflow_status = "scheduled"
            next_scheduled_publish_at = scheduled_publish_at

        connection.execute(
            """
            UPDATE editorial_articles
            SET workflow_status = ?,
                review_note = ?,
                scheduled_publish_at = ?,
                submitted_at = ?,
                approved_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                next_workflow_status,
                next_review_note,
                next_scheduled_publish_at,
                next_submitted_at,
                next_approved_at,
                timestamp,
                editorial_id,
            ),
        )
        connection.commit()
    return get_editorial_article(editorial_id)


def create_editorial_from_upload(filename: str, raw_bytes: bytes) -> dict:
    normalized = _extract_upload_content(filename, raw_bytes)
    if not normalized:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    title = Path(filename).stem
    lines = normalized.splitlines()
    if lines:
        first_meaningful = next((line.strip() for line in lines if line.strip()), "")
        if first_meaningful.startswith("#"):
            title = re.sub(r"^#+\s*", "", first_meaningful).strip() or title
            normalized = "\n".join(lines[1:]).strip() or normalized
        elif len(first_meaningful) <= 48:
            title = first_meaningful

    return create_editorial_article(
        {
            "title": title,
            "source_markdown": normalized,
            "content_markdown": normalized,
        }
    )


def auto_format_editorial_article(editorial_id: int, payload: dict | None = None) -> dict:
    request_payload = payload or {}
    with connection_scope() as connection:
        current = dict(_fetch_editorial_row(connection, editorial_id))
        if current["status"] == "published":
            raise HTTPException(status_code=400, detail="Published editorial article cannot be auto-formatted")

        source_markdown = str(request_payload.get("source_markdown") or current.get("source_markdown") or current.get("content_markdown") or "").strip()
        if not source_markdown:
            raise HTTPException(status_code=400, detail="Source content is empty")

        layout_mode = _normalize_layout_mode(request_payload.get("layout_mode") or current.get("layout_mode"))
        formatting_notes = str(request_payload.get("formatting_notes") or current.get("formatting_notes") or "").strip()
        tag_payload = _load_tag_payload(current.get("tag_payload_json"))
        formatted = ai_service.auto_format_editorial_markdown(
            title=current.get("title") or "",
            source_markdown=source_markdown,
            excerpt=current.get("excerpt") or "",
            main_topic=current.get("main_topic") or "",
            article_type=current.get("article_type") or "",
            organization=current.get("organization") or "",
            tags=[tag.get("name") for tag in tag_payload],
            layout_mode=layout_mode,
            formatting_notes=formatting_notes,
        )

        content_markdown = str(formatted.get("markdown") or "").strip()
        if not content_markdown:
            raise HTTPException(status_code=502, detail="Auto-formatting returned empty content")

        timestamp = _now_iso()
        plain_text_content = strip_markdown(content_markdown)
        excerpt = _extract_excerpt(plain_text_content)
        connection.execute(
            """
            UPDATE editorial_articles
            SET source_markdown = ?,
                layout_mode = ?,
                formatting_notes = ?,
                formatter_model = ?,
                last_formatted_at = ?,
                content_markdown = ?,
                plain_text_content = ?,
                excerpt = ?,
                html_web = NULL,
                html_wechat = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                source_markdown,
                layout_mode,
                formatting_notes or None,
                formatted.get("model"),
                timestamp,
                content_markdown,
                plain_text_content,
                excerpt,
                timestamp,
                editorial_id,
            ),
        )
        connection.commit()
    return get_editorial_article(editorial_id)


def generate_editorial_tags(editorial_id: int) -> dict:
    with connection_scope() as connection:
        row = dict(_fetch_editorial_row(connection, editorial_id))
        known_categories = {
            item["name"]: item["category"]
            for item in connection.execute("SELECT name, category FROM tags").fetchall()
        }

        heuristic_entries = _derive_tag_entries(
            {
                "title": row.get("title") or "",
                "main_topic": row.get("main_topic") or "",
                "excerpt": row.get("excerpt") or "",
                "content": row.get("plain_text_content") or "",
                "search_text": row.get("plain_text_content") or "",
                "tag_text": "",
                "article_type": row.get("article_type") or "",
                "series_or_column": "",
                "people_text": "",
                "org_text": row.get("organization") or "",
            },
            known_categories,
        )

        ai_payload = ai_service.suggest_editorial_metadata(
            row.get("title") or "",
            row.get("plain_text_content") or row.get("content_markdown") or "",
        )

        ai_entries: list[tuple[str, str, float]] = []
        for item in ai_payload.get("tags", []):
            if not isinstance(item, dict):
                continue
            raw_name = str(item.get("name") or "").strip()
            if not raw_name:
                continue
            category = str(item.get("category") or "topic").strip()
            confidence = item.get("confidence", 0.72)
            ai_entries.append((raw_name[:32], category, float(confidence)))

        merged_tags = _dedupe_tags([*heuristic_entries, *ai_entries])

        excerpt = row.get("excerpt") or ""
        ai_excerpt = str(ai_payload.get("excerpt") or "").strip()
        if ai_excerpt:
            excerpt = ai_excerpt[:180]

        article_type = row.get("article_type")
        ai_article_type = str(ai_payload.get("article_type") or "").strip()
        if ai_article_type:
            article_type = ai_article_type[:32]

        main_topic = row.get("main_topic")
        ai_main_topic = str(ai_payload.get("main_topic") or "").strip()
        if ai_main_topic:
            main_topic = ai_main_topic[:48]

        column_slug = row.get("primary_column_slug")
        ai_column_slug = str(ai_payload.get("column_slug") or "").strip()
        if ai_column_slug in VALID_COLUMN_SLUGS:
            column_slug = ai_column_slug
        if not column_slug:
            column_slug = _infer_column_slug(
                {
                    "title": row.get("title"),
                    "article_type": article_type,
                    "main_topic": main_topic,
                    "organization": row.get("organization"),
                },
                merged_tags,
            )

        connection.execute(
            """
            UPDATE editorial_articles
            SET excerpt = ?, article_type = ?, main_topic = ?, primary_column_slug = ?,
                tag_payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                excerpt or _extract_excerpt(row.get("plain_text_content") or ""),
                article_type,
                main_topic,
                column_slug,
                json.dumps(merged_tags, ensure_ascii=False),
                _now_iso(),
                editorial_id,
            ),
        )
        connection.commit()

    return get_editorial_article(editorial_id)


def render_editorial_html(editorial_id: int) -> dict:
    article = get_editorial_article(editorial_id)
    if not article["tags"]:
        article = generate_editorial_tags(editorial_id)

    rendered = render_editorial_package(article, article["tags"])
    updated_at = _now_iso()
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE editorial_articles
            SET excerpt = ?, html_web = ?, html_wechat = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                rendered["summary"],
                rendered["html_web"],
                rendered["html_wechat"],
                updated_at,
                editorial_id,
            ),
        )
        connection.commit()

    return {
        "article_id": editorial_id,
        "html_web": rendered["html_web"],
        "html_wechat": rendered["html_wechat"],
        "summary": rendered["summary"],
    }


def export_editorial_html(editorial_id: int, variant: str) -> tuple[str, str]:
    article = get_editorial_article(editorial_id)
    if not article["html_web"] or not article["html_wechat"]:
        render_editorial_html(editorial_id)
        article = get_editorial_article(editorial_id)

    if variant not in {"web", "wechat"}:
        raise HTTPException(status_code=400, detail="Unsupported export variant")

    html = article["html_web"] if variant == "web" else article["html_wechat"]
    if not html:
        raise HTTPException(status_code=404, detail="HTML export is not ready")
    filename = f"{article['slug']}-{variant}.html"
    return filename, html


def publish_editorial_article(editorial_id: int) -> dict:
    article = get_editorial_article(editorial_id)
    if not article["tags"]:
        article = generate_editorial_tags(editorial_id)
    if not article["html_web"] or not article["html_wechat"]:
        render_editorial_html(editorial_id)
        article = get_editorial_article(editorial_id)

    now = _now_iso()
    with connection_scope() as connection:
        row = dict(_fetch_editorial_row(connection, editorial_id))
        public_slug = _unique_slug(
            connection,
            "articles",
            slugify(row["slug"])[:80],
            exclude_id=row["article_id"],
        )
        tag_payload = _load_tag_payload(row["tag_payload_json"])
        tag_text = " | ".join(
            tag["name"] for tag in tag_payload if tag.get("category") in {"industry", "topic", "type", "series"}
        )
        plain_text = row["plain_text_content"]
        organization = row.get("organization") or ""
        source_url = row.get("source_url") or None

        if row["article_id"] and connection.execute(
            "SELECT id FROM articles WHERE id = ?",
            (row["article_id"],),
        ).fetchone():
            article_id = row["article_id"]
            connection.execute(
                """
                UPDATE articles
                SET doc_id = ?, slug = ?, relative_path = ?, source = ?, source_mode = ?, title = ?,
                    publish_date = ?, link = ?, content = ?, excerpt = ?, main_topic = ?, article_type = ?,
                    series_or_column = ?, primary_org_name = ?, tag_text = ?, people_text = '',
                    org_text = ?, search_text = ?, word_count = ?, cover_image_path = NULL,
                    access_level = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    hashlib.sha1(f"editorial:{editorial_id}:{public_slug}".encode("utf-8")).hexdigest()[:20],
                    public_slug,
                    f"editorial/{public_slug}.md",
                    "editorial",
                    "cms",
                    row["title"],
                    row["publish_date"],
                    source_url,
                    plain_text,
                    row["excerpt"],
                    row["main_topic"],
                    row["article_type"],
                    "内容后台",
                    organization or None,
                    tag_text,
                    organization,
                    f"{row['title']} {row['excerpt'] or ''} {plain_text[:4000]}",
                    _word_count(plain_text),
                    row.get("access_level") or "public",
                    now,
                    article_id,
                ),
            )
        else:
            connection.execute(
                """
                INSERT INTO articles (
                    doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                    content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                    tag_text, people_text, org_text, search_text, word_count, cover_image_path, access_level,
                    view_count, is_featured, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, NULL, ?, 0, 0, ?, ?)
                """,
                (
                    hashlib.sha1(f"editorial:{editorial_id}:{public_slug}".encode("utf-8")).hexdigest()[:20],
                    public_slug,
                    f"editorial/{public_slug}.md",
                    "editorial",
                    "cms",
                    row["title"],
                    row["publish_date"],
                    source_url,
                    plain_text,
                    row["excerpt"],
                    row["main_topic"],
                    row["article_type"],
                    "内容后台",
                    organization or None,
                    tag_text,
                    organization,
                    f"{row['title']} {row['excerpt'] or ''} {plain_text[:4000]}",
                    _word_count(plain_text),
                    row.get("access_level") or "public",
                    now,
                    now,
                ),
            )
            article_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])

        connection.execute("DELETE FROM article_tags WHERE article_id = ?", (article_id,))
        for tag in tag_payload:
            tag_id = _ensure_tag(
                connection,
                tag.get("name") or "",
                tag.get("category") or "topic",
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO article_tags (article_id, tag_id, confidence)
                VALUES (?, ?, ?)
                """,
                (article_id, tag_id, float(tag.get("confidence") or 0.7)),
            )

        connection.execute("DELETE FROM article_columns WHERE article_id = ?", (article_id,))
        column_slug = row.get("primary_column_slug")
        if column_slug in VALID_COLUMN_SLUGS:
            column_row = connection.execute(
                "SELECT id FROM columns WHERE slug = ?",
                (column_slug,),
            ).fetchone()
            if column_row is not None:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO article_columns (article_id, column_id, is_featured, sort_order)
                    VALUES (?, ?, 0, 0)
                    """,
                    (article_id, column_row["id"]),
                )

        connection.execute(
            """
            UPDATE tags
            SET article_count = (
                SELECT COUNT(*)
                FROM article_tags
                WHERE tag_id = tags.id
            )
            """
        )
        connection.execute("DELETE FROM tags WHERE article_count <= 0")
        connection.execute(
            """
            UPDATE editorial_articles
            SET article_id = ?,
                slug = ?,
                status = 'published',
                workflow_status = 'published',
                approved_at = COALESCE(approved_at, ?),
                published_at = COALESCE(published_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (article_id, public_slug, now, now, now, editorial_id),
        )
        connection.commit()

    refresh_search_cache()
    return {
        "editorial_id": editorial_id,
        "article_id": article_id,
        "status": "published",
        "article_url": f"/article/{article_id}",
        "updated_at": now,
    }
