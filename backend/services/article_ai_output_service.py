from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.database import connection_scope
from backend.services.article_asset_service import build_article_source_hash
from backend.services.membership_service import access_level_label
from backend.services.article_visibility_service import is_hidden_low_value_article


def preview_markdown(content: str, paragraph_limit: int = 4, char_limit: int = 900) -> str:
    paragraphs = [part.strip() for part in str(content or "").splitlines() if part.strip()]
    if not paragraphs:
        return ""

    collected: list[str] = []
    used_chars = 0
    for paragraph in paragraphs:
        if len(collected) >= paragraph_limit or used_chars >= char_limit:
            break
        remaining = max(char_limit - used_chars, 0)
        if remaining <= 0:
            break
        if len(paragraph) > remaining:
            collected.append(f"{paragraph[:remaining].rstrip()}...")
            break
        collected.append(paragraph)
        used_chars += len(paragraph)
    return "\n\n".join(collected)


def build_current_article_source_hash(article_row: Any) -> str:
    return build_article_source_hash(
        {
            "id": article_row["id"],
            "title": article_row["title"],
            "excerpt": article_row["excerpt"],
            "main_topic": article_row["main_topic"],
            "content": article_row["content"],
            "access_level": article_row["access_level"] or "public",
        }
    )


def fetch_current_article_row(connection, article_id: int):
    row = connection.execute(
        """
        SELECT
            id,
            title,
            slug,
            publish_date,
            source,
            excerpt,
            main_topic,
            article_type,
            primary_org_name,
            access_level,
            link,
            relative_path,
            content
        FROM articles
        WHERE id = ?
        """,
        (article_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return row


def fetch_latest_article_ai_output_row(connection, article_id: int, *, source_hash: str | None = None):
    params: list[object] = [article_id]
    filters = ["article_id = ?"]
    if source_hash:
        filters.append("source_hash = ?")
        params.append(source_hash)
    return connection.execute(
        f"""
        SELECT *
        FROM article_ai_outputs
        WHERE {' AND '.join(filters)}
        ORDER BY
            CASE status WHEN 'completed' THEN 0 WHEN 'running' THEN 1 WHEN 'failed' THEN 2 ELSE 3 END,
            COALESCE(completed_at, updated_at, created_at) DESC,
            updated_at DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()


def _is_ready(row, status_key: str, value_key: str) -> bool:
    if row is None:
        return False
    return row[status_key] == "completed" and bool(str(row[value_key] or "").strip())


def _translation_ready(row) -> bool:
    if row is None or row["translation_status"] != "completed":
        return False
    return bool(str(row["formatted_markdown_en"] or row["translation_content_en"] or "").strip())


def _serialize_source_article(row, ai_row, current_source_hash: str) -> dict[str, Any]:
    access_level = row["access_level"] or "public"
    return {
        "article_id": row["id"],
        "title": row["title"],
        "publish_date": row["publish_date"],
        "excerpt": row["excerpt"] or "",
        "source": row["source"] or "business",
        "link": row["link"],
        "article_type": row["article_type"],
        "main_topic": row["main_topic"],
        "primary_org_name": row["primary_org_name"],
        "access_level": access_level,
        "access_label": access_level_label(access_level),
        "ai": {
            "status": ai_row["status"] if ai_row else "pending",
            "summary_ready": _is_ready(ai_row, "summary_status", "summary_zh"),
            "format_ready": _is_ready(ai_row, "format_status", "formatted_markdown_zh"),
            "translation_ready": _translation_ready(ai_row),
            "source_hash": ai_row["source_hash"] if ai_row else None,
            "source_hash_matches_current": bool(ai_row and ai_row["source_hash"] == current_source_hash),
            "updated_at": ai_row["updated_at"] if ai_row else None,
        },
    }


def _serialize_ai_output(article_row, ai_row, current_source_hash: str) -> dict[str, Any]:
    access_level = article_row["access_level"] or "public"
    return {
        "article_id": article_row["id"],
        "title": article_row["title"],
        "publish_date": article_row["publish_date"],
        "excerpt": article_row["excerpt"] or "",
        "source": article_row["source"] or "business",
        "link": article_row["link"],
        "article_type": article_row["article_type"],
        "main_topic": article_row["main_topic"],
        "primary_org_name": article_row["primary_org_name"],
        "access_level": access_level,
        "access_label": access_level_label(access_level),
        "source_hash": ai_row["source_hash"] if ai_row else None,
        "source_hash_matches_current": bool(ai_row and ai_row["source_hash"] == current_source_hash),
        "status": ai_row["status"] if ai_row else "pending",
        "summary_ready": _is_ready(ai_row, "summary_status", "summary_zh"),
        "format_ready": _is_ready(ai_row, "format_status", "formatted_markdown_zh"),
        "translation_ready": _translation_ready(ai_row),
        "summary_zh": ai_row["summary_zh"] if ai_row else None,
        "summary_html_zh": ai_row["summary_html_zh"] if ai_row else None,
        "formatted_markdown_zh": ai_row["formatted_markdown_zh"] if ai_row else None,
        "formatted_markdown_en": ai_row["formatted_markdown_en"] if ai_row else None,
        "translation_title_en": ai_row["translation_title_en"] if ai_row else None,
        "translation_excerpt_en": ai_row["translation_excerpt_en"] if ai_row else None,
        "translation_summary_en": ai_row["translation_summary_en"] if ai_row else None,
        "summary_html_en": ai_row["summary_html_en"] if ai_row else None,
        "translation_content_en": ai_row["translation_content_en"] if ai_row else None,
        "html_web_zh": ai_row["html_web_zh"] if ai_row else None,
        "html_wechat_zh": ai_row["html_wechat_zh"] if ai_row else None,
        "html_web_en": ai_row["html_web_en"] if ai_row else None,
        "html_wechat_en": ai_row["html_wechat_en"] if ai_row else None,
        "translation_model": ai_row["translation_model"] if ai_row else None,
        "format_model": ai_row["format_model"] if ai_row else None,
        "updated_at": ai_row["updated_at"] if ai_row else None,
    }


def list_article_ai_source_articles(*, query: str = "", limit: int = 12) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 40))
    query_text = str(query or "").strip()
    params: list[object] = []
    where_sql = "WHERE a.source != 'editorial'"
    if query_text:
        like = f"%{query_text}%"
        where_sql += " AND (a.title LIKE ? OR COALESCE(a.excerpt, '') LIKE ? OR COALESCE(a.main_topic, '') LIKE ?)"
        params.extend([like, like, like])

    with connection_scope() as connection:
        rows = connection.execute(
            f"""
            SELECT
                a.id,
                a.title,
                a.slug,
                a.publish_date,
                a.source,
                a.excerpt,
                a.main_topic,
                a.article_type,
                a.primary_org_name,
                a.access_level,
                a.link,
                a.relative_path,
                a.content
            FROM articles a
            {where_sql}
            ORDER BY a.publish_date DESC, a.id DESC
            LIMIT ?
            """,
            (*params, safe_limit),
        ).fetchall()

        payload: list[dict[str, Any]] = []
        for row in rows:
            if is_hidden_low_value_article(row):
                continue
            current_source_hash = build_current_article_source_hash(row)
            ai_row = fetch_latest_article_ai_output_row(connection, row["id"], source_hash=current_source_hash)
            if ai_row is None:
                ai_row = fetch_latest_article_ai_output_row(connection, row["id"])
            payload.append(_serialize_source_article(row, ai_row, current_source_hash))
        return payload


def get_article_ai_output_detail(article_id: int) -> dict[str, Any]:
    with connection_scope() as connection:
        article_row = fetch_current_article_row(connection, article_id)
        current_source_hash = build_current_article_source_hash(article_row)
        ai_row = fetch_latest_article_ai_output_row(connection, article_id, source_hash=current_source_hash)
        if ai_row is None:
            ai_row = fetch_latest_article_ai_output_row(connection, article_id)
    return _serialize_ai_output(article_row, ai_row, current_source_hash)
