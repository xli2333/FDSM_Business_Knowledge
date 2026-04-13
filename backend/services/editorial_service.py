from __future__ import annotations

import hashlib
import html
import io
import json
import re
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from backend.config import COLUMN_DEFINITIONS
from backend.database import connection_scope, ensure_runtime_tables
from backend.services.article_ai_output_service import (
    build_current_article_source_hash,
    fetch_latest_article_ai_output_row,
    get_article_ai_output_detail,
    list_article_ai_source_articles,
)
from backend.services import ai_service
from backend.services.content_operations_service import search_content_operation_candidates
from backend.services.fudan_wechat_renderer import (
    FudanWechatRenderError,
    build_fudan_render_item,
    render_fudan_wechat,
)
from backend.services.display_markdown_service import normalize_summary_display_markdown
from backend.services.html_renderer import strip_markdown
from backend.services.membership_service import access_level_label, normalize_access_level
from backend.services.rag_engine import refresh_search_cache
from backend.services.summary_preview_service import is_summary_preview_html, render_summary_preview_html
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


EDITOR_SOURCE_AI = "ai_formatted"
EDITOR_SOURCE_MANUAL = "manual_edited"
EDITOR_SOURCE_IMPORTED = "imported_legacy_html"
DRAFT_BOX_STATE_ACTIVE = "active"
DRAFT_BOX_STATE_ARCHIVED = "archived"
EDITORIAL_GENERIC_ENTITY_NAMES = {
    "Fudan Business Knowledge",
    "Fudan Business Knowledge Editorial Desk",
    "复旦商业知识",
    "复旦商业知识编辑部",
}
EDITORIAL_SIGNAL_RULES: tuple[tuple[str, str, tuple[str, ...], float], ...] = (
    ("数据治理", "topic", ("数据治理", "安全治理", "治理体系"), 0.93),
    ("数据安全", "topic", ("数据安全", "信息安全", "安全基础设施"), 0.92),
    ("数据泄露", "topic", ("数据泄露", "泄露事件", "撞库攻击", "数据灾难"), 0.94),
    ("隐私保护", "topic", ("隐私保护", "个人信息保护", "基因隐私", "隐私恐慌"), 0.9),
    ("网络安全", "topic", ("网络安全", "黑客", "撞库", "身份验证"), 0.84),
    ("破产重组", "topic", ("破产保护", "chapter 11", "破产重组", "破产法院"), 0.82),
    ("基因检测", "industry", ("基因检测", "消费级基因检测", "遗传检测"), 0.94),
    ("生物科技", "industry", ("生物科技", "生物技术", "生命科学"), 0.88),
    ("医疗健康", "industry", ("医疗健康", "远程医疗", "制药", "药物研发"), 0.84),
)
EDITORIAL_ENTITY_STOPWORDS = {
    "DNA",
    "CEO",
    "SPAC",
    "FY2021",
    "FY2022",
    "FY2023",
    "FY2024",
    "FY2025",
    "JSON",
}
EDITORIAL_MULTIWORD_ENTITY_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]+|[A-Z]{2,}|[0-9]+[A-Za-z][A-Za-z0-9.+-]*)"
    r"(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}|[0-9]+[A-Za-z][A-Za-z0-9.+-]*)){1,4}\b"
)
EDITORIAL_MIXED_ENTITY_PATTERN = re.compile(r"\b[0-9]+[A-Za-z][A-Za-z0-9.+-]*\b")
EDITORIAL_ACRONYM_PATTERN = re.compile(r"[（(]([A-Z][A-Z0-9&.+-]{1,12})[)）]")


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


def _normalize_draft_box_state(value: str | None) -> str:
    draft_box_state = (value or "").strip() or DRAFT_BOX_STATE_ACTIVE
    if draft_box_state not in {DRAFT_BOX_STATE_ACTIVE, DRAFT_BOX_STATE_ARCHIVED}:
        raise HTTPException(status_code=400, detail="Unsupported draft box state")
    return draft_box_state


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


def _load_json_array(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _load_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_column_slug(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if text in VALID_COLUMN_SLUGS else None


def _tag_signature(tag: dict[str, Any]) -> tuple[str, str]:
    return (
        str(tag.get("name") or "").strip().lower(),
        str(tag.get("category") or "topic").strip().lower() or "topic",
    )


def _is_low_signal_tag_name(value: str | None) -> bool:
    name = str(value or "").strip()
    compact = re.sub(r"\s+", "", name)
    if not compact:
        return True
    lowered = compact.lower()
    if lowered in {"作者", "编辑", "记者", "文章"}:
        return True
    if re.fullmatch(r"[a-z]", lowered):
        return True
    if re.fullmatch(r"[a-z](author|作者)", lowered):
        return True
    return False


def _admin_entity_key(item: dict[str, Any]) -> str:
    return f"{item.get('entity_type') or 'entity'}:{item.get('id') or ''}:{item.get('slug') or ''}"


def _merge_admin_entities(*groups: list[dict], limit: int = 12) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for group in groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            key = _admin_entity_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def _normalize_render_sensitive_value(field: str, value: Any) -> Any:
    if field in {
        "title",
        "author",
        "organization",
        "source_url",
        "source_markdown",
        "content_markdown",
        "formatting_notes",
    }:
        return str(value or "").strip()
    if field == "layout_mode":
        return _normalize_layout_mode(value)
    return value


def _render_sensitive_field_changed(field: str, previous_value: Any, next_value: Any) -> bool:
    return _normalize_render_sensitive_value(field, previous_value) != _normalize_render_sensitive_value(field, next_value)


def _editorial_phrase_present(raw_text: str, compact_text: str, phrase: str) -> bool:
    normalized = str(phrase or "").strip().lower()
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9.+\- ]+", normalized):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
        return re.search(pattern, raw_text) is not None
    return re.sub(r"\s+", "", normalized) in compact_text


def _normalize_editorial_entity_name(value: str | None) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    name = name.strip(".,:;!?()[]{}<>\"'“”‘’")
    return name[:48]


def _extract_editorial_signal_entries(
    title: str | None,
    excerpt: str | None,
    content: str | None,
    organization: str | None = None,
) -> list[tuple[str, str, float]]:
    raw_text = "\n".join(part for part in (title or "", excerpt or "", content or "") if str(part or "").strip()).lower()
    compact_text = re.sub(r"\s+", "", raw_text)
    entries: list[tuple[str, str, float]] = []

    for name, category, phrases, confidence in EDITORIAL_SIGNAL_RULES:
        if any(_editorial_phrase_present(raw_text, compact_text, phrase) for phrase in phrases):
            entries.append((name, category, confidence))

    entity_counter: Counter[str] = Counter()
    source_text = "\n".join(part for part in (title or "", excerpt or "", content or "", organization or "") if str(part or "").strip())
    for pattern in (EDITORIAL_MULTIWORD_ENTITY_PATTERN, EDITORIAL_MIXED_ENTITY_PATTERN, EDITORIAL_ACRONYM_PATTERN):
        for matched in pattern.findall(source_text):
            candidate = matched if isinstance(matched, str) else matched[0]
            normalized = _normalize_editorial_entity_name(candidate)
            if (
                not normalized
                or normalized in EDITORIAL_ENTITY_STOPWORDS
                or normalized in EDITORIAL_GENERIC_ENTITY_NAMES
                or _is_low_signal_tag_name(normalized)
            ):
                continue
            entity_counter[normalized] += 1

    ranked_entities = sorted(entity_counter.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    for index, (name, count) in enumerate(ranked_entities[:5]):
        confidence = 0.86 if index == 0 or count > 1 else 0.8
        entries.append((name, "entity", confidence))

    return entries


def _serialize_editorial_row(row) -> dict:
    tags = _load_tag_payload(row["tag_payload_json"])
    ai_tags = _load_tag_payload(row["tag_suggestion_payload_json"] if "tag_suggestion_payload_json" in row.keys() else None)
    removed_tags = _load_tag_payload(row["removed_tag_payload_json"] if "removed_tag_payload_json" in row.keys() else None)
    workflow_status = _normalize_workflow_status(row["workflow_status"])
    draft_box_state = _normalize_draft_box_state(row["draft_box_state"] if "draft_box_state" in row.keys() else None)
    raw_summary_markdown = (
        row["summary_markdown"]
        if "summary_markdown" in row.keys() and row["summary_markdown"]
        else row["excerpt"]
    )
    summary_markdown = _normalize_summary_markdown(raw_summary_markdown) or None
    raw_summary_html = (
        row["summary_html"]
        if "summary_html" in row.keys() and row["summary_html"]
        else _build_summary_editorial_html(summary_markdown)
    )
    summary_html = str(raw_summary_html or "").strip() or None
    published_summary_html = (
        str((row["published_summary_html"] if "published_summary_html" in row.keys() else None) or "").strip()
        or summary_html
        if row["status"] == "published"
        else str((row["published_summary_html"] if "published_summary_html" in row.keys() else None) or "").strip() or None
    )
    summary_editor_document = _load_editor_document(
        row["summary_editor_document_json"] if "summary_editor_document_json" in row.keys() else None
    )
    if not summary_editor_document and summary_html:
        summary_editor_document = _build_editor_document_payload(summary_html)
    summary_model = str((row["summary_model"] if "summary_model" in row.keys() else None) or "").strip() or None
    summary_updated_at = str((row["summary_updated_at"] if "summary_updated_at" in row.keys() else None) or "").strip() or None
    manual_summary_html_backup = (
        str((row["manual_summary_html_backup"] if "manual_summary_html_backup" in row.keys() else None) or "").strip()
        or None
    )
    raw_final_html = (
        row["final_html"]
        if "final_html" in row.keys() and row["final_html"]
        else (
            row["published_final_html"]
            if "published_final_html" in row.keys() and row["published_final_html"]
            else row["html_web"] or row["html_wechat"] or ""
        )
    )
    final_html = str(raw_final_html or "").strip() or None
    published_final_html = (
        str((row["published_final_html"] if "published_final_html" in row.keys() else None) or "").strip() or None
    )
    editor_document = _load_editor_document(row["editor_document_json"] if "editor_document_json" in row.keys() else None)
    editor_source = str((row["editor_source"] if "editor_source" in row.keys() else None) or "").strip() or None
    editor_updated_at = str((row["editor_updated_at"] if "editor_updated_at" in row.keys() else None) or "").strip() or None
    manual_final_html_backup = (
        str((row["manual_final_html_backup"] if "manual_final_html_backup" in row.keys() else None) or "").strip() or None
    )
    if not editor_document and final_html:
        editor_document = _build_editor_document_payload(final_html)
    if not editor_source and final_html:
        editor_source = EDITOR_SOURCE_IMPORTED
    html_web = str((row["html_web"] or final_html or row["html_wechat"] or "").strip() or "") or None
    html_wechat = str((row["html_wechat"] or final_html or row["html_web"] or "").strip() or "") or None
    publish_validation = _load_validation_payload(
        row["publish_validation_json"] if "publish_validation_json" in row.keys() else None
    )
    published_at = row["published_at"] if "published_at" in row.keys() else None
    updated_at = row["updated_at"] if "updated_at" in row.keys() else None
    has_unpublished_changes = bool(
        published_final_html
        and (
            final_html != published_final_html
            or (published_at and editor_updated_at and editor_updated_at > published_at)
        )
    )
    summary_has_unpublished_changes = bool(
        published_summary_html
        and (
            summary_html != published_summary_html
            or (published_at and summary_updated_at and summary_updated_at > published_at)
        )
    )
    is_reopened_from_published = bool(row["status"] == "published" and workflow_status != "published")
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
        "primary_column_ai_slug": row["primary_column_ai_slug"] if "primary_column_ai_slug" in row.keys() else None,
        "primary_column_manual": bool(row["primary_column_manual"]) if "primary_column_manual" in row.keys() else False,
        "article_type": row["article_type"],
        "main_topic": row["main_topic"],
        "access_level": row["access_level"] or "public",
        "access_label": access_level_label(row["access_level"] or "public"),
        "workflow_status": workflow_status,
        "workflow_label": workflow_status_label(workflow_status),
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
        "summary_markdown": summary_markdown,
        "summary_html": summary_html,
        "published_summary_html": published_summary_html,
        "summary_editor_document": summary_editor_document,
        "summary_model": summary_model,
        "summary_updated_at": summary_updated_at,
        "summary_has_unpublished_changes": summary_has_unpublished_changes,
        "manual_summary_html_backup": manual_summary_html_backup,
        "has_summary_backup": bool(manual_summary_html_backup),
        "content_markdown": row["content_markdown"],
        "plain_text_content": row["plain_text_content"],
        "excerpt": row["excerpt"],
        "tags": tags,
        "ai_tags": ai_tags,
        "removed_tags": removed_tags,
        "has_unpublished_changes": has_unpublished_changes,
        "draft_box_state": draft_box_state,
        "is_reopened_from_published": is_reopened_from_published,
        "final_html": final_html,
        "published_final_html": published_final_html,
        "html_web": html_web,
        "html_wechat": html_wechat,
        "editor_document": editor_document,
        "editor_source": editor_source,
        "editor_updated_at": editor_updated_at,
        "is_manual_edit": editor_source == EDITOR_SOURCE_MANUAL,
        "manual_final_html_backup": manual_final_html_backup,
        "has_manual_backup": bool(manual_final_html_backup),
        "render_metadata": _load_render_metadata(row["render_metadata_json"] if "render_metadata_json" in row.keys() else None),
        "publish_validation": publish_validation or _build_publish_validation(
            {
                "title": row["title"],
                "source_markdown": row["source_markdown"] if "source_markdown" in row.keys() else "",
                "content_markdown": row["content_markdown"],
                "tags": tags,
                "primary_column_slug": row["primary_column_slug"],
                "final_html": final_html,
            }
        ),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": updated_at,
        "published_at": published_at,
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
        if not name or _is_low_signal_tag_name(name):
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


def _normalize_tag_payload(raw: list[dict] | None) -> list[dict]:
    entries: list[tuple[str, str, float]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("name") or "").strip()
        if not raw_name or _is_low_signal_tag_name(raw_name):
            continue
        category = str(item.get("category") or "topic").strip() or "topic"
        try:
            confidence = float(item.get("confidence", 0.72))
        except (TypeError, ValueError):
            confidence = 0.72
        entries.append((raw_name[:32], category, confidence))
    return _dedupe_tags(entries)


def _load_tag_payload(raw: str | None) -> list[dict]:
    return _normalize_tag_payload(_load_json_array(raw))


def _load_render_metadata(raw: str | None) -> dict[str, Any]:
    payload = _load_json_object(raw)
    render_plan = payload.get("render_plan")
    metadata = payload.get("metadata")
    warnings = payload.get("warnings")
    return {
        "render_plan": render_plan if isinstance(render_plan, dict) else {},
        "metadata": metadata if isinstance(metadata, dict) else {},
        "warnings": [str(item).strip() for item in warnings if str(item).strip()] if isinstance(warnings, list) else [],
    }


def _load_validation_payload(raw: str | None) -> list[dict]:
    payload = _load_json_array(raw)
    issues: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        message = str(item.get("message") or "").strip()
        if code and message:
            issues.append({"code": code, "message": message})
    return issues


def _load_editor_document(raw: str | None) -> dict[str, Any]:
    payload = _load_json_object(raw)
    return payload if payload else {}


def _build_editor_document_payload(final_html: str | None, document: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_document = document if isinstance(document, dict) else {}
    if normalized_document:
        payload = dict(normalized_document)
        payload.setdefault("schema", "tiptap-v1")
        return payload

    html_value = str(final_html or "").strip()
    if not html_value:
        return {}
    return {
        "schema": "html-fallback-v1",
        "html": html_value,
    }


def _sanitize_editor_html(raw_html: str | None) -> str:
    html_value = str(raw_html or "").strip()
    if not html_value:
        return ""

    sanitized = re.sub(r"<\s*script\b[^>]*>.*?<\s*/script\s*>", "", html_value, flags=re.I | re.S)
    sanitized = re.sub(r"\s+on[a-zA-Z-]+\s*=\s*(['\"]).*?\1", "", sanitized, flags=re.I | re.S)
    sanitized = re.sub(r"\s+on[a-zA-Z-]+\s*=\s*[^\s>]+", "", sanitized, flags=re.I)
    sanitized = re.sub(r"\s+(contenteditable|spellcheck|draggable)\s*=\s*(['\"]).*?\2", "", sanitized, flags=re.I | re.S)
    sanitized = re.sub(r"\s+(contenteditable|spellcheck|draggable)\s*=\s*[^\s>]+", "", sanitized, flags=re.I)
    return sanitized.strip()


def _html_to_plain_text(raw_html: str | None) -> str:
    html_value = str(raw_html or "").strip()
    if not html_value:
        return ""

    text = html_value.replace("\r\n", "\n")
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*/(p|div|section|article|blockquote|li|ul|ol|h1|h2|h3|h4|h5|h6)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_summary_markdown(raw_text: str | None) -> str:
    source = str(raw_text or "").strip()
    if not source:
        return ""

    normalized = normalize_summary_display_markdown(source, "zh").strip()
    hybrid_candidate = re.sub(
        r"\n{3,}",
        "\n\n",
        ai_service.normalize_editorial_summary_output(source).strip(),
    ).strip()

    source_has_list = bool(re.search(r"(?m)^[-*+]\s+", source))
    normalized_has_list = bool(re.search(r"(?m)^[-*+]\s+", normalized))
    hybrid_has_list = bool(re.search(r"(?m)^[-*+]\s+", hybrid_candidate))
    normalized_length = ai_service.editorial_summary_visible_length(normalized)
    hybrid_length = ai_service.editorial_summary_visible_length(hybrid_candidate)

    if source_has_list and hybrid_has_list and (not normalized_has_list or normalized_length < ai_service.EDITORIAL_SUMMARY_MIN_CHARS):
        return hybrid_candidate
    if hybrid_length > normalized_length and (
        normalized_length < ai_service.EDITORIAL_SUMMARY_MIN_CHARS
        or ("**" in hybrid_candidate and "**" not in normalized)
    ):
        return hybrid_candidate
    return normalized


def _build_summary_editorial_html(raw_text: str | None) -> str | None:
    normalized_summary = _normalize_summary_markdown(raw_text)
    if not normalized_summary:
        return None
    return render_summary_preview_html(normalized_summary, language="zh")


def _build_summary_editorial_assets(title: str | None, content: str | None) -> dict[str, str | None]:
    source_text = str(content or "").strip()
    payload = ai_service.summarize_article_payload(str(title or "").strip(), source_text)
    summary_markdown = _normalize_summary_markdown(
        ai_service.normalize_editorial_summary_output(payload.get("summary") or "")
    )
    if not summary_markdown:
        summary_markdown = _normalize_summary_markdown(
            ai_service.normalize_editorial_summary_output(ai_service.build_extractive_summary(source_text))
        )
    return {
        "summary_markdown": summary_markdown or None,
        "summary_html": _build_summary_editorial_html(summary_markdown),
        "summary_model": str(payload.get("model") or "").strip() or None,
    }


def _build_basic_editor_html(title: str, content: str) -> str:
    safe_title = html.escape(str(title or "").strip() or "未命名文章")
    paragraphs = [
        f"<p>{html.escape(part)}</p>"
        for part in re.split(r"\n{2,}", str(content or "").replace("\r\n", "\n").replace("\r", "\n"))
        if part.strip()
    ]
    if not paragraphs:
        paragraphs = ["<p>当前正文尚无可编辑内容。</p>"]
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /></head><body>"
        f"<article><h1>{safe_title}</h1>{''.join(paragraphs)}</article></body></html>"
    )


def _compute_removed_tags(ai_tags: list[dict], selected_tags: list[dict]) -> list[dict]:
    selected_signatures = {_tag_signature(tag) for tag in selected_tags}
    return [tag for tag in ai_tags if _tag_signature(tag) not in selected_signatures]


def _apply_removed_tags(ai_tags: list[dict], removed_tags: list[dict]) -> list[dict]:
    removed_signatures = {_tag_signature(tag) for tag in removed_tags}
    return [tag for tag in ai_tags if _tag_signature(tag) not in removed_signatures]


def _build_publish_validation(article: dict[str, Any]) -> list[dict]:
    issues: list[dict] = []
    if not str(article.get("title") or "").strip():
        issues.append({"code": "missing_title", "message": "缺少标题"})
    if not str(article.get("source_markdown") or "").strip():
        issues.append({"code": "missing_source", "message": "缺少原稿"})
    if not str(article.get("content_markdown") or "").strip():
        issues.append({"code": "missing_formatted_markdown", "message": "缺少排版稿 Markdown"})
    if not str(article.get("final_html") or article.get("html_web") or "").strip():
        issues.append({"code": "missing_final_html", "message": "最终 HTML 尚未生成"})
    if not article.get("tags"):
        issues.append({"code": "missing_tags", "message": "至少保留一个标签后才能发布"})
    if not _normalize_column_slug(article.get("primary_column_slug")):
        issues.append({"code": "missing_primary_column", "message": "请选择栏目"})
    return issues


def _validation_payload_json(article: dict[str, Any]) -> str:
    return json.dumps(_build_publish_validation(article), ensure_ascii=False)


def _render_metadata_payload(rendered: dict[str, Any]) -> dict[str, Any]:
    return {
        "render_plan": rendered.get("renderPlan") if isinstance(rendered.get("renderPlan"), dict) else {},
        "metadata": rendered.get("metadata") if isinstance(rendered.get("metadata"), dict) else {},
        "warnings": [str(item).strip() for item in rendered.get("warnings", []) if str(item).strip()],
    }


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


def _build_editorial_render_input(article: dict[str, Any]) -> dict[str, Any]:
    return build_fudan_render_item(
        title=article.get("title") or "",
        content_markdown=article.get("content_markdown") or "",
        summary=article.get("excerpt") or "",
        source_url=article.get("source_url"),
        author=article.get("author") or "",
        editor=article.get("organization") or "",
        opening_highlight_mode="smart_lead",
        omit_credits=False,
        render_plan=article.get("render_plan") if isinstance(article.get("render_plan"), dict) else None,
    )


def _render_editorial_preview(article: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    try:
        rendered = render_fudan_wechat(_build_editorial_render_input(article))
    except FudanWechatRenderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    final_html = str(rendered.get("previewHtml") or rendered.get("contentHtml") or "").strip()
    if not final_html:
        raise HTTPException(status_code=502, detail="Rendered final HTML is empty")
    return final_html, _render_metadata_payload(rendered)


def _extract_body_html(raw_html: str | None) -> str:
    html_value = str(raw_html or "").strip()
    if not html_value:
        return ""
    match = re.search(r"<body[^>]*>(?P<body>[\s\S]*?)</body>", html_value, flags=re.I)
    return match.group("body") if match else html_value


def _should_rebuild_legacy_wechat_preview(raw_html: str | None, title: str | None) -> bool:
    html_value = str(raw_html or "").strip()
    title_value = str(title or "").strip()
    if not html_value or not title_value:
        return False
    if "wechat-preview-shell" not in html_value:
        return False
    return title_value not in _extract_body_html(html_value)


def _repair_legacy_editorial_html_if_needed(connection, row):
    current = dict(row)
    final_html = str(current.get("final_html") or current.get("html_web") or current.get("html_wechat") or "").strip()
    if not _should_rebuild_legacy_wechat_preview(final_html, current.get("title")):
        return row
    if str(current.get("editor_source") or "").strip() == EDITOR_SOURCE_MANUAL:
        return row

    render_metadata = _load_render_metadata(current.get("render_metadata_json"))
    render_plan = render_metadata.get("render_plan") if isinstance(render_metadata.get("render_plan"), dict) else {}
    if not render_plan:
        return row

    try:
        repaired_html, repaired_metadata = _render_editorial_preview({**current, "render_plan": render_plan})
    except HTTPException:
        return row

    published_final_html = str(current.get("published_final_html") or "").strip()
    should_refresh_published_html = bool(
        current.get("status") == "published"
        and (not published_final_html or _should_rebuild_legacy_wechat_preview(published_final_html, current.get("title")))
    )

    connection.execute(
        """
        UPDATE editorial_articles
        SET final_html = ?,
            html_web = ?,
            html_wechat = ?,
            editor_document_json = ?,
            editor_source = ?,
            render_metadata_json = ?,
            published_final_html = CASE WHEN ? THEN ? ELSE published_final_html END
        WHERE id = ?
        """,
        (
            repaired_html,
            repaired_html,
            repaired_html,
            json.dumps(_build_editor_document_payload(repaired_html), ensure_ascii=False),
            EDITOR_SOURCE_AI,
            json.dumps(repaired_metadata, ensure_ascii=False),
            1 if should_refresh_published_html else 0,
            repaired_html,
            int(current["id"]),
        ),
    )
    return _fetch_editorial_row(connection, int(current["id"]))


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
    draft_box_state: str | None = DRAFT_BOX_STATE_ACTIVE,
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
    if draft_box_state and str(draft_box_state).strip() != "all":
        filters.append("draft_box_state = ?")
        params.append(_normalize_draft_box_state(draft_box_state))
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connection_scope() as connection:
        rows = connection.execute(query.format(where_sql=where_sql), (*params, safe_limit)).fetchall()
    return [_serialize_editorial_row(row) for row in rows]


def get_editorial_article(editorial_id: int) -> dict:
    with connection_scope() as connection:
        row = _repair_legacy_editorial_html_if_needed(connection, _fetch_editorial_row(connection, editorial_id))
        selected_topics = _resolve_effective_editorial_topics(connection, row)
    payload = _serialize_editorial_row(row)
    payload["selected_topics"] = selected_topics
    payload["selected_topic_ids"] = [int(item["id"]) for item in selected_topics if item.get("id") is not None]
    topic_hint = " ".join(
        part
        for part in (
            payload.get("title") or "",
            payload.get("main_topic") or "",
            payload.get("article_type") or "",
        )
        if str(part or "").strip()
    ).strip()
    payload["topic_candidates"] = _merge_admin_entities(
        selected_topics,
        list_editorial_topic_candidates(query=topic_hint, limit=8),
        limit=12,
    )
    if payload.get("source_article_id"):
        payload["source_article_ai"] = get_article_ai_output_detail(int(payload["source_article_id"]))
    else:
        payload["source_article_ai"] = None
    return payload


def delete_editorial_article(editorial_id: int) -> dict:
    with connection_scope() as connection:
        row = dict(_fetch_editorial_row(connection, editorial_id))
        if row.get("status") == "published" or row.get("article_id"):
            raise HTTPException(status_code=400, detail="Published editorial articles cannot be deleted from the draft box")
        connection.execute("DELETE FROM editorial_article_topics WHERE editorial_id = ?", (editorial_id,))
        connection.execute("DELETE FROM editorial_articles WHERE id = ?", (editorial_id,))
        connection.commit()
    return {
        "editorial_id": editorial_id,
        "deleted": True,
    }

def reopen_published_article_to_editorial_draft_box(article_id: int) -> dict:
    timestamp = _now_iso()
    with connection_scope() as connection:
        source_row = _fetch_source_article_row(connection, article_id)
        current_source_hash = build_current_article_source_hash(source_row)
        ai_row = fetch_latest_article_ai_output_row(connection, article_id, source_hash=current_source_hash)
        if ai_row is None:
            ai_row = fetch_latest_article_ai_output_row(connection, article_id)

        source_markdown = str(source_row.get("content") or "").strip()
        content_markdown = str((ai_row["formatted_markdown_zh"] if ai_row is not None else None) or "").strip() or source_markdown
        if not source_markdown and not content_markdown:
            raise HTTPException(status_code=400, detail="Current article content is empty and cannot be reopened into the draft box")

        tag_payload = _fetch_source_article_tags(connection, article_id)
        source_topics = _fetch_source_article_topics(connection, article_id)
        column_slug = _fetch_source_article_column_slug(connection, article_id) or _infer_column_slug(source_row, tag_payload)
        access_level = normalize_access_level(source_row.get("access_level"))
        organization = ""
        formatter_model = str((ai_row["format_model"] if ai_row is not None else None) or "").strip() or None
        live_html = _resolve_source_article_live_html(connection, source_row, ai_row)
        plain_text_content = _html_to_plain_text(live_html) or strip_markdown(content_markdown)
        source_summary_markdown = _normalize_summary_markdown(
            ai_service.normalize_editorial_summary_output(
                str((ai_row["summary_zh"] if ai_row is not None else None) or source_row.get("excerpt") or "").strip()
            )
        )
        source_summary_html = str((ai_row["summary_html_zh"] if ai_row is not None else None) or "").strip()
        if not is_summary_preview_html(source_summary_html):
            source_summary_html = _build_summary_editorial_html(source_summary_markdown) or ""
        excerpt = _extract_excerpt(strip_markdown(source_summary_markdown) or plain_text_content, limit=180)
        existing_row = _fetch_latest_editorial_row_by_article_id(connection, article_id)

        if existing_row is not None:
            current = dict(existing_row)
            ai_tags = _load_tag_payload(current.get("tag_suggestion_payload_json")) or tag_payload
            selected_tags = _load_tag_payload(current.get("tag_payload_json")) or tag_payload
            removed_tags = _compute_removed_tags(ai_tags, selected_tags)
            published_summary_html = str(current.get("published_summary_html") or "").strip() or source_summary_html
            working_summary_html = str(current.get("summary_html") or "").strip() or published_summary_html
            current_summary_markdown = _normalize_summary_markdown(current.get("summary_markdown") or source_summary_markdown)
            if not working_summary_html and current_summary_markdown:
                working_summary_html = _build_summary_editorial_html(current_summary_markdown) or ""
            published_final_html = (
                _sanitize_editor_html(live_html)
                or str(current.get("published_final_html") or "").strip()
                or str(current.get("final_html") or current.get("html_web") or current.get("html_wechat") or "").strip()
            )
            working_final_html = (
                str(current.get("final_html") or current.get("html_web") or current.get("html_wechat") or "").strip()
                or published_final_html
            )
            plain_text_content = _html_to_plain_text(working_final_html) or strip_markdown(
                str(current.get("content_markdown") or content_markdown or source_markdown)
            )
            excerpt = _extract_excerpt(strip_markdown(current_summary_markdown) or plain_text_content, limit=180)
            current_column_slug = _normalize_column_slug(current.get("primary_column_slug")) or column_slug
            current_source_markdown = str(current.get("source_markdown") or source_markdown or content_markdown).strip()
            current_content_markdown = str(current.get("content_markdown") or content_markdown or source_markdown).strip()
            current_summary_editor_document = _build_editor_document_payload(
                working_summary_html,
                _load_editor_document(current.get("summary_editor_document_json")),
            )
            current_summary_updated_at = current.get("summary_updated_at")
            if working_summary_html == published_summary_html:
                current_summary_updated_at = None
            current_editor_document = _build_editor_document_payload(
                working_final_html,
                _load_editor_document(current.get("editor_document_json")),
            )
            current_editor_source = str(current.get("editor_source") or "").strip() or EDITOR_SOURCE_IMPORTED
            current_editor_updated_at = current.get("editor_updated_at")
            if working_final_html == published_final_html:
                current_editor_updated_at = None
            validation_payload = _validation_payload_json(
                {
                    "title": source_row["title"],
                    "source_markdown": current_source_markdown,
                    "content_markdown": current_content_markdown,
                    "tags": selected_tags,
                    "primary_column_slug": current_column_slug,
                    "final_html": working_final_html,
                }
            )
            connection.execute(
                """
                UPDATE editorial_articles
                SET source_article_id = ?,
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
                    summary_markdown = ?,
                    summary_html = ?,
                    published_summary_html = ?,
                    summary_editor_document_json = ?,
                    summary_model = ?,
                    summary_updated_at = ?,
                    content_markdown = ?,
                    plain_text_content = ?,
                    excerpt = ?,
                    tag_suggestion_payload_json = ?,
                    tag_payload_json = ?,
                    removed_tag_payload_json = ?,
                    primary_column_ai_slug = ?,
                    primary_column_manual = ?,
                    final_html = ?,
                    published_final_html = ?,
                    editor_document_json = ?,
                    editor_source = ?,
                    editor_updated_at = ?,
                    html_web = ?,
                    html_wechat = ?,
                    formatter_model = ?,
                    ai_synced_at = ?,
                    draft_box_state = ?,
                    status = 'published',
                    workflow_status = 'draft',
                    publish_validation_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    article_id,
                    source_row["title"],
                    current.get("author") or "Fudan Business Knowledge Editorial Desk",
                    current.get("organization") or organization,
                    _normalize_publish_date(source_row.get("publish_date")),
                    source_row.get("link"),
                    current_column_slug,
                    source_row.get("article_type"),
                    source_row.get("main_topic"),
                    access_level,
                    current_source_markdown,
                    current_summary_markdown or None,
                    working_summary_html or None,
                    published_summary_html or None,
                    json.dumps(current_summary_editor_document, ensure_ascii=False),
                    current.get("summary_model"),
                    current_summary_updated_at,
                    current_content_markdown,
                    plain_text_content,
                    excerpt,
                    json.dumps(ai_tags, ensure_ascii=False),
                    json.dumps(selected_tags, ensure_ascii=False),
                    json.dumps(removed_tags, ensure_ascii=False),
                    column_slug,
                    1 if current_column_slug else 0,
                    working_final_html,
                    published_final_html,
                    json.dumps(current_editor_document, ensure_ascii=False),
                    current_editor_source,
                    current_editor_updated_at,
                    working_final_html,
                    working_final_html,
                    formatter_model or current.get("formatter_model"),
                    timestamp,
                    DRAFT_BOX_STATE_ACTIVE,
                    validation_payload,
                    timestamp,
                    current["id"],
                ),
            )
            if (
                not bool(current.get("topic_selection_manual"))
                and not _fetch_editorial_selected_topics(connection, int(current["id"]))
                and source_topics
            ):
                _replace_editorial_selected_topics(
                    connection,
                    int(current["id"]),
                    [int(item["id"]) for item in source_topics],
                    manual=False,
                )
            connection.commit()
            return get_editorial_article(int(current["id"]))

        selected_tags = tag_payload
        summary_editor_document = _build_editor_document_payload(source_summary_html)
        editor_document = _build_editor_document_payload(live_html)
        validation_payload = _validation_payload_json(
            {
                "title": source_row["title"],
                "source_markdown": source_markdown or content_markdown,
                "content_markdown": content_markdown or source_markdown,
                "tags": selected_tags,
                "primary_column_slug": column_slug,
                "final_html": live_html,
            }
        )
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
                summary_markdown,
                summary_html,
                published_summary_html,
                summary_editor_document_json,
                summary_model,
                summary_updated_at,
                layout_mode,
                formatting_notes,
                formatter_model,
                last_formatted_at,
                content_markdown,
                plain_text_content,
                excerpt,
                tag_suggestion_payload_json,
                tag_payload_json,
                removed_tag_payload_json,
                primary_column_ai_slug,
                primary_column_manual,
                final_html,
                published_final_html,
                editor_document_json,
                editor_source,
                editor_updated_at,
                manual_final_html_backup,
                html_web,
                html_wechat,
                render_metadata_json,
                publish_validation_json,
                status,
                draft_box_state,
                workflow_status,
                ai_synced_at,
                created_at,
                updated_at,
                published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id,
                article_id,
                unique_slug,
                source_row["title"],
                None,
                "Fudan Business Knowledge Editorial Desk",
                organization,
                _normalize_publish_date(source_row.get("publish_date")),
                source_row.get("link"),
                None,
                column_slug,
                source_row.get("article_type"),
                source_row.get("main_topic"),
                access_level,
                source_markdown or content_markdown,
                source_summary_markdown or None,
                source_summary_html or None,
                source_summary_html or None,
                json.dumps(summary_editor_document, ensure_ascii=False),
                "source_ai_output" if source_summary_html else None,
                None,
                "auto",
                None,
                formatter_model,
                timestamp if formatter_model else None,
                content_markdown or source_markdown,
                plain_text_content,
                excerpt,
                json.dumps(tag_payload, ensure_ascii=False),
                json.dumps(selected_tags, ensure_ascii=False),
                "[]",
                column_slug,
                1 if column_slug else 0,
                live_html,
                live_html,
                json.dumps(editor_document, ensure_ascii=False),
                EDITOR_SOURCE_IMPORTED,
                None,
                None,
                live_html,
                live_html,
                "{}",
                validation_payload,
                "published",
                DRAFT_BOX_STATE_ACTIVE,
                "draft",
                timestamp,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        editorial_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        if source_topics:
            _replace_editorial_selected_topics(
                connection,
                editorial_id,
                [int(item["id"]) for item in source_topics],
                manual=False,
            )
        connection.commit()
    return get_editorial_article(editorial_id)


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


def _fetch_source_article_topics(connection, article_id: int) -> list[dict]:
    rows = connection.execute(
        """
        SELECT t.id, t.slug, t.title, t.description, t.type
        FROM topic_articles ta
        JOIN topics t ON t.id = ta.topic_id
        WHERE ta.article_id = ? AND t.status = 'published'
        ORDER BY ta.sort_order ASC, t.title ASC
        """,
        (article_id,),
    ).fetchall()
    return [
        {
            "entity_type": "topic",
            "id": row["id"],
            "slug": row["slug"],
            "title": row["title"],
            "subtitle": row["type"],
            "description": row["description"] or "",
        }
        for row in rows
    ]


def _fetch_editorial_selected_topics(connection, editorial_id: int) -> list[dict]:
    rows = connection.execute(
        """
        SELECT t.id, t.slug, t.title, t.description, t.type
        FROM editorial_article_topics eat
        JOIN topics t ON t.id = eat.topic_id
        WHERE eat.editorial_id = ? AND t.status = 'published'
        ORDER BY eat.sort_order ASC, t.title ASC
        """,
        (editorial_id,),
    ).fetchall()
    return [
        {
            "entity_type": "topic",
            "id": row["id"],
            "slug": row["slug"],
            "title": row["title"],
            "subtitle": row["type"],
            "description": row["description"] or "",
        }
        for row in rows
    ]


def _resolve_effective_editorial_topics(connection, row) -> list[dict]:
    editorial_id = int(row["id"])
    selected_topics = _fetch_editorial_selected_topics(connection, editorial_id)
    manual_selection = bool(row["topic_selection_manual"]) if "topic_selection_manual" in row.keys() else False
    if selected_topics:
        return selected_topics
    if manual_selection:
        return []
    source_article_id = row["source_article_id"] if "source_article_id" in row.keys() else None
    article_id = row["article_id"] if "article_id" in row.keys() else None
    effective_article_id = source_article_id or article_id
    if effective_article_id:
        return _fetch_source_article_topics(connection, int(effective_article_id))
    return []


def _replace_editorial_selected_topics(
    connection,
    editorial_id: int,
    topic_ids: list[int] | None,
    *,
    manual: bool = True,
) -> None:
    normalized_ids: list[int] = []
    seen_ids: set[int] = set()
    for value in topic_ids or []:
        try:
            topic_id = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid topic id") from exc
        if topic_id in seen_ids:
            continue
        seen_ids.add(topic_id)
        normalized_ids.append(topic_id)

    connection.execute("DELETE FROM editorial_article_topics WHERE editorial_id = ?", (editorial_id,))
    if not normalized_ids:
        connection.execute(
            "UPDATE editorial_articles SET topic_selection_manual = ? WHERE id = ?",
            (1 if manual else 0, editorial_id),
        )
        return

    placeholders = ",".join("?" for _ in normalized_ids)
    topic_rows = connection.execute(
        f"""
        SELECT id
        FROM topics
        WHERE status = 'published' AND id IN ({placeholders})
        """,
        normalized_ids,
    ).fetchall()
    valid_ids = {int(row["id"]) for row in topic_rows}
    if len(valid_ids) != len(normalized_ids):
        raise HTTPException(status_code=400, detail="One or more selected topics are unavailable")

    timestamp = _now_iso()
    connection.executemany(
        """
        INSERT INTO editorial_article_topics (editorial_id, topic_id, sort_order, created_at)
        VALUES (?, ?, ?, ?)
        """,
        [(editorial_id, topic_id, index, timestamp) for index, topic_id in enumerate(normalized_ids)],
    )
    connection.execute(
        "UPDATE editorial_articles SET topic_selection_manual = ? WHERE id = ?",
        (1 if manual else 0, editorial_id),
    )


def _sync_article_topics_from_editorial(connection, article_id: int, topics: list[dict]) -> None:
    connection.execute("DELETE FROM topic_articles WHERE article_id = ?", (article_id,))
    if not topics:
        return
    connection.executemany(
        """
        INSERT OR REPLACE INTO topic_articles (topic_id, article_id, sort_order, editor_note)
        VALUES (?, ?, ?, ?)
        """,
        [
            (int(topic["id"]), article_id, index, "editorial")
            for index, topic in enumerate(topics)
            if topic.get("id")
        ],
    )


def _fetch_latest_editorial_row_by_article_id(connection, article_id: int):
    return connection.execute(
        """
        SELECT *
        FROM editorial_articles
        WHERE article_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()


def _fetch_published_editorial_html(connection, article_id: int) -> str | None:
    row = connection.execute(
        """
        SELECT COALESCE(published_final_html, final_html, html_web, html_wechat) AS final_html
        FROM editorial_articles
        WHERE article_id = ? AND status = 'published'
        ORDER BY published_at DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()
    if row is None:
        return None
    html_value = str(row["final_html"] or "").strip()
    return html_value or None


def _resolve_source_article_live_html(connection, source_row: dict, ai_row) -> str:
    editorial_html = _fetch_published_editorial_html(connection, source_row["id"])
    if editorial_html:
        return _sanitize_editor_html(editorial_html)

    if ai_row is not None:
        for field in ("html_wechat_zh", "html_web_zh"):
            candidate = _sanitize_editor_html(ai_row[field])
            if candidate:
                return candidate

    fallback_text = str(
        (ai_row["formatted_markdown_zh"] if ai_row is not None else None)
        or source_row.get("content")
        or source_row.get("excerpt")
        or ""
    ).strip()
    return _build_basic_editor_html(source_row.get("title") or "", fallback_text)


def list_editorial_source_articles(query: str = "", limit: int = 12) -> list[dict]:
    return list_article_ai_source_articles(query=query, limit=limit)


def get_editorial_source_ai_output(article_id: int) -> dict:
    return get_article_ai_output_detail(article_id)


def list_editorial_topic_candidates(query: str = "", limit: int = 12) -> list[dict]:
    return search_content_operation_candidates("topic", query=query, limit=limit)


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
        source_topics = _fetch_source_article_topics(connection, source_article_id)
        column_slug = _fetch_source_article_column_slug(connection, source_article_id) or "insights"
        plain_text_content = strip_markdown(formatted_markdown)
        summary_excerpt = strip_markdown(str(ai_output.get("summary_zh") or "")).strip()
        summary_markdown = _normalize_summary_markdown(
            ai_service.normalize_editorial_summary_output(
                str(ai_output.get("summary_zh") or source_row.get("excerpt") or "").strip()
            )
        )
        summary_html = str(ai_output.get("summary_html_zh") or "").strip()
        if not is_summary_preview_html(summary_html):
            summary_html = _build_summary_editorial_html(summary_markdown) or ""
        excerpt = (
            _extract_excerpt(summary_excerpt, limit=180)
            if summary_excerpt
            else source_row.get("excerpt") or _extract_excerpt(plain_text_content)
        )
        source_markdown = str(source_row.get("content") or formatted_markdown).strip()
        access_level = normalize_access_level(source_row.get("access_level"))
        organization = ""
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
                    summary_markdown = ?,
                    summary_html = ?,
                    summary_editor_document_json = ?,
                    summary_model = ?,
                    summary_updated_at = ?,
                    layout_mode = ?,
                    formatting_notes = NULL,
                    formatter_model = ?,
                    last_formatted_at = ?,
                    content_markdown = ?,
                    plain_text_content = ?,
                    excerpt = ?,
                    tag_suggestion_payload_json = ?,
                    tag_payload_json = ?,
                    removed_tag_payload_json = '[]',
                    primary_column_ai_slug = ?,
                    primary_column_manual = 0,
                    final_html = NULL,
                    html_web = NULL,
                    html_wechat = NULL,
                    render_metadata_json = '{}',
                    publish_validation_json = ?,
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
                    summary_markdown or None,
                    summary_html or None,
                    json.dumps(_build_editor_document_payload(summary_html), ensure_ascii=False) if summary_html else "{}",
                    "source_ai_output" if summary_html else None,
                    now if summary_html else None,
                    "auto",
                    str(ai_output.get("format_model") or ""),
                    now,
                    formatted_markdown,
                    plain_text_content,
                    excerpt,
                    json.dumps(tag_payload, ensure_ascii=False),
                    json.dumps(tag_payload, ensure_ascii=False),
                    column_slug,
                    json.dumps(
                        _build_publish_validation(
                            {
                                "title": source_row["title"],
                                "source_markdown": source_markdown,
                                "content_markdown": formatted_markdown,
                                "tags": tag_payload,
                                "primary_column_slug": column_slug,
                                "final_html": None,
                            }
                        ),
                        ensure_ascii=False,
                    ),
                    now,
                    now,
                    int(editorial_id),
                ),
            )
            if (
                not bool(current.get("topic_selection_manual"))
                and not _fetch_editorial_selected_topics(connection, int(editorial_id))
                and source_topics
            ):
                _replace_editorial_selected_topics(
                    connection,
                    int(editorial_id),
                    [int(item["id"]) for item in source_topics],
                    manual=False,
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
                summary_markdown,
                summary_html,
                published_summary_html,
                summary_editor_document_json,
                summary_model,
                summary_updated_at,
                layout_mode,
                formatting_notes,
                formatter_model,
                last_formatted_at,
                content_markdown,
                plain_text_content,
                excerpt,
                tag_suggestion_payload_json,
                tag_payload_json,
                removed_tag_payload_json,
                primary_column_ai_slug,
                primary_column_manual,
                final_html,
                html_web,
                html_wechat,
                render_metadata_json,
                publish_validation_json,
                status,
                draft_box_state,
                workflow_status,
                ai_synced_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                source_article_id,
                unique_slug,
                source_row["title"],
                None,
                author,
                organization,
                _normalize_publish_date(source_row.get("publish_date")),
                source_row.get("link"),
                None,
                column_slug,
                source_row.get("article_type"),
                source_row.get("main_topic"),
                access_level,
                source_markdown,
                summary_markdown or None,
                summary_html or None,
                None,
                json.dumps(_build_editor_document_payload(summary_html), ensure_ascii=False) if summary_html else "{}",
                "source_ai_output" if summary_html else None,
                now if summary_html else None,
                "auto",
                None,
                str(ai_output.get("format_model") or ""),
                now,
                formatted_markdown,
                plain_text_content,
                excerpt,
                json.dumps(tag_payload, ensure_ascii=False),
                json.dumps(tag_payload, ensure_ascii=False),
                "[]",
                column_slug,
                0,
                None,
                None,
                None,
                "{}",
                json.dumps(
                    _build_publish_validation(
                        {
                            "title": source_row["title"],
                            "source_markdown": source_markdown,
                            "content_markdown": formatted_markdown,
                            "tags": tag_payload,
                            "primary_column_slug": column_slug,
                            "final_html": None,
                        }
                    ),
                    ensure_ascii=False,
                ),
                "draft",
                DRAFT_BOX_STATE_ACTIVE,
                "draft",
                now,
                now,
                now,
            ),
        )
        editorial_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        if source_topics:
            _replace_editorial_selected_topics(
                connection,
                editorial_id,
                [int(item["id"]) for item in source_topics],
                manual=False,
            )
        connection.commit()
    return get_editorial_article(editorial_id)


def create_editorial_article(payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    content_markdown = str(payload.get("content_markdown") or "").strip()
    source_markdown = str(payload.get("source_markdown") or "").strip()
    selected_tags = _normalize_tag_payload(payload.get("tags"))
    summary_markdown = _normalize_summary_markdown(payload.get("summary_markdown") or "")
    summary_html = _sanitize_editor_html(payload.get("summary_html"))
    if not summary_html and summary_markdown:
        summary_html = _build_summary_editorial_html(summary_markdown) or ""
    summary_editor_document = _build_editor_document_payload(summary_html, payload.get("summary_editor_document"))
    final_html = _sanitize_editor_html(payload.get("final_html"))
    editor_document = _build_editor_document_payload(final_html, payload.get("editor_document"))
    editor_source = EDITOR_SOURCE_MANUAL if final_html else None
    if not content_markdown and source_markdown:
        content_markdown = source_markdown
    if not source_markdown and content_markdown:
        source_markdown = content_markdown
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if not content_markdown:
        raise HTTPException(status_code=400, detail="Content is required")

    now = _now_iso()
    plain_text_content = _html_to_plain_text(final_html) if final_html else strip_markdown(content_markdown)
    summary_text = strip_markdown(summary_markdown) if summary_markdown else ""
    excerpt = _extract_excerpt(summary_text or plain_text_content, limit=180)
    access_level = normalize_access_level(payload.get("access_level"))
    layout_mode = _normalize_layout_mode(payload.get("layout_mode"))
    formatting_notes = str(payload.get("formatting_notes") or "").strip() or None
    primary_column_slug = _normalize_column_slug(payload.get("primary_column_slug"))
    primary_column_manual = bool(payload.get("primary_column_manual")) if primary_column_slug else False
    validation_payload = _build_publish_validation(
        {
            "title": title,
            "source_markdown": source_markdown,
            "content_markdown": content_markdown,
            "tags": selected_tags,
            "primary_column_slug": primary_column_slug,
            "final_html": final_html or None,
        }
    )

    with connection_scope() as connection:
        desired_slug = slugify((payload.get("slug") or title).strip())[:80]
        unique_slug = _unique_slug(connection, "editorial_articles", desired_slug)
        connection.execute(
            """
            INSERT INTO editorial_articles (
                slug, title, subtitle, author, organization, publish_date, source_url,
                cover_image_url, primary_column_slug, article_type, main_topic, access_level,
                source_markdown, summary_markdown, summary_html, published_summary_html, summary_editor_document_json,
                summary_model, summary_updated_at, manual_summary_html_backup,
                layout_mode, formatting_notes, content_markdown, plain_text_content, excerpt,
                tag_suggestion_payload_json, tag_payload_json, removed_tag_payload_json, primary_column_ai_slug, primary_column_manual,
                final_html, published_final_html, editor_document_json, editor_source, editor_updated_at, manual_final_html_backup,
                html_web, html_wechat, render_metadata_json, publish_validation_json,
                status, draft_box_state, workflow_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                primary_column_slug,
                payload.get("article_type"),
                payload.get("main_topic"),
                access_level,
                source_markdown,
                summary_markdown or None,
                summary_html or None,
                None,
                json.dumps(summary_editor_document, ensure_ascii=False),
                None,
                now if summary_html else None,
                None,
                layout_mode,
                formatting_notes,
                content_markdown,
                plain_text_content,
                excerpt,
                json.dumps(selected_tags, ensure_ascii=False),
                json.dumps(selected_tags, ensure_ascii=False),
                "[]",
                None,
                1 if primary_column_manual else 0,
                final_html or None,
                None,
                json.dumps(editor_document, ensure_ascii=False),
                editor_source,
                now if final_html else None,
                None,
                final_html or None,
                final_html or None,
                "{}",
                json.dumps(validation_payload, ensure_ascii=False),
                "draft",
                DRAFT_BOX_STATE_ACTIVE,
                "draft",
                now,
                now,
            ),
        )
        editorial_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        if payload.get("selected_topic_ids") is not None:
            _replace_editorial_selected_topics(connection, int(editorial_id), payload.get("selected_topic_ids") or [])
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
        "primary_column_manual",
        "article_type",
        "main_topic",
        "access_level",
        "source_markdown",
        "summary_markdown",
        "layout_mode",
        "formatting_notes",
        "content_markdown",
        "tags",
        "selected_topic_ids",
        "summary_html",
        "summary_editor_document",
        "final_html",
        "editor_document",
    }
    updates = {key: value for key, value in payload.items() if key in allowed_fields and value is not None}
    if not updates and payload.get("slug") is None:
        return get_editorial_article(editorial_id)

    with connection_scope() as connection:
        current = dict(_fetch_editorial_row(connection, editorial_id))
        original_current = dict(current)
        if "title" in updates and not str(updates["title"]).strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        if "content_markdown" in updates and not str(updates["content_markdown"]).strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        if "source_markdown" in updates and not str(updates["source_markdown"]).strip():
            raise HTTPException(status_code=400, detail="Source content cannot be empty")
        if "summary_html" in updates and not str(updates["summary_html"]).strip():
            raise HTTPException(status_code=400, detail="Summary HTML cannot be empty")
        if "final_html" in updates and not str(updates["final_html"]).strip():
            raise HTTPException(status_code=400, detail="Final HTML cannot be empty")

        ai_tags = _load_tag_payload(current.get("tag_suggestion_payload_json"))
        selected_tags = _load_tag_payload(current.get("tag_payload_json"))
        manual_summary_update = "summary_html" in updates or "summary_editor_document" in updates
        manual_editor_update = "final_html" in updates or "editor_document" in updates
        previous_summary_html = str(current.get("summary_html") or "").strip()
        previous_final_html = str(current.get("final_html") or current.get("html_web") or current.get("html_wechat") or "").strip()
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
        current["primary_column_slug"] = _normalize_column_slug(current.get("primary_column_slug"))
        current["source_markdown"] = str(current.get("source_markdown") or current.get("content_markdown") or "").strip()
        current["content_markdown"] = str(current.get("content_markdown") or current.get("source_markdown") or "").strip()
        current["plain_text_content"] = strip_markdown(current.get("content_markdown") or "")
        current["summary_markdown"] = _normalize_summary_markdown(current.get("summary_markdown") or "")
        current["excerpt"] = _extract_excerpt(strip_markdown(current["summary_markdown"]) or current["plain_text_content"], limit=180)
        current["updated_at"] = _now_iso()
        if current.get("formatting_notes") is not None:
            current["formatting_notes"] = str(current.get("formatting_notes") or "").strip() or None
        if "tags" in updates:
            selected_tags = _normalize_tag_payload(updates.get("tags"))
            if not ai_tags:
                ai_tags = selected_tags
                current["tag_suggestion_payload_json"] = json.dumps(ai_tags, ensure_ascii=False)
        if "primary_column_slug" in updates and payload.get("primary_column_manual") is None:
            current["primary_column_manual"] = 1 if current.get("primary_column_slug") else 0
        elif payload.get("primary_column_manual") is not None:
            current["primary_column_manual"] = 1 if payload.get("primary_column_manual") and current.get("primary_column_slug") else 0
        else:
            current["primary_column_manual"] = 1 if current.get("primary_column_manual") and current.get("primary_column_slug") else 0

        removed_tags = _compute_removed_tags(ai_tags, selected_tags)
        current["tag_suggestion_payload_json"] = current.get("tag_suggestion_payload_json") or json.dumps(ai_tags, ensure_ascii=False)
        current["tag_payload_json"] = json.dumps(selected_tags, ensure_ascii=False)
        current["removed_tag_payload_json"] = json.dumps(removed_tags, ensure_ascii=False)
        if "summary_markdown" in updates and not manual_summary_update:
            regenerated_summary_html = _build_summary_editorial_html(current.get("summary_markdown"))
            current["summary_html"] = regenerated_summary_html
            current["summary_editor_document_json"] = (
                json.dumps(_build_editor_document_payload(regenerated_summary_html), ensure_ascii=False)
                if regenerated_summary_html
                else "{}"
            )
            current["summary_model"] = None
            current["summary_updated_at"] = current["updated_at"] if regenerated_summary_html else None

        render_sensitive_fields = {
            "title",
            "author",
            "organization",
            "source_url",
            "source_markdown",
            "content_markdown",
            "layout_mode",
            "formatting_notes",
        }
        clear_render = any(
            field in updates and _render_sensitive_field_changed(field, original_current.get(field), current.get(field))
            for field in render_sensitive_fields
        )
        if manual_summary_update:
            sanitized_summary_html = _sanitize_editor_html(updates.get("summary_html") or current.get("summary_html"))
            if not sanitized_summary_html:
                raise HTTPException(status_code=400, detail="Summary HTML cannot be empty")
            current["summary_html"] = sanitized_summary_html
            current["summary_markdown"] = _normalize_summary_markdown(
                updates.get("summary_markdown") or _html_to_plain_text(sanitized_summary_html)
            )
            current["summary_editor_document_json"] = json.dumps(
                _build_editor_document_payload(
                    sanitized_summary_html,
                    updates.get("summary_editor_document") if isinstance(updates.get("summary_editor_document"), dict) else None,
                ),
                ensure_ascii=False,
            )
            current["summary_model"] = None
            current["summary_updated_at"] = current["updated_at"]
            current["excerpt"] = _extract_excerpt(
                strip_markdown(current["summary_markdown"]) or current["plain_text_content"],
                limit=180,
            )
            if previous_summary_html and previous_summary_html != sanitized_summary_html:
                current["manual_summary_html_backup"] = previous_summary_html
        if manual_editor_update:
            sanitized_final_html = _sanitize_editor_html(updates.get("final_html") or current.get("final_html") or current.get("html_web"))
            if not sanitized_final_html:
                raise HTTPException(status_code=400, detail="Final HTML cannot be empty")
            current["final_html"] = sanitized_final_html
            current["html_web"] = sanitized_final_html
            current["html_wechat"] = sanitized_final_html
            current["plain_text_content"] = _html_to_plain_text(sanitized_final_html) or strip_markdown(current.get("content_markdown") or "")
            current["excerpt"] = _extract_excerpt(
                strip_markdown(current.get("summary_markdown") or "") or current["plain_text_content"],
                limit=180,
            )
            current["editor_document_json"] = json.dumps(
                _build_editor_document_payload(
                    sanitized_final_html,
                    updates.get("editor_document") if isinstance(updates.get("editor_document"), dict) else None,
                ),
                ensure_ascii=False,
            )
            current["editor_source"] = EDITOR_SOURCE_MANUAL
            current["editor_updated_at"] = current["updated_at"]
            if previous_final_html and previous_final_html != sanitized_final_html:
                current["manual_final_html_backup"] = previous_final_html
        elif clear_render:
            if previous_summary_html:
                current["manual_summary_html_backup"] = previous_summary_html
            current["summary_markdown"] = None
            current["summary_html"] = None
            current["summary_editor_document_json"] = "{}"
            current["summary_model"] = None
            current["summary_updated_at"] = None
            if previous_final_html:
                current["manual_final_html_backup"] = previous_final_html
            current["final_html"] = None
            current["html_web"] = None
            current["html_wechat"] = None
            current["editor_document_json"] = "{}"
            current["editor_source"] = None
            current["editor_updated_at"] = None
            current["render_metadata_json"] = "{}"
        elif current.get("status") == "published" and updates:
            current["editor_updated_at"] = current["updated_at"]
        current["publish_validation_json"] = _validation_payload_json(
            {
                "title": current.get("title"),
                "source_markdown": current.get("source_markdown"),
                "content_markdown": current.get("content_markdown"),
                "tags": selected_tags,
                "primary_column_slug": current.get("primary_column_slug"),
                "final_html": current.get("final_html") or current.get("html_web"),
            }
        )

        connection.execute(
            """
            UPDATE editorial_articles
            SET slug = ?, title = ?, subtitle = ?, author = ?, organization = ?, publish_date = ?,
                source_url = ?, cover_image_url = ?, primary_column_slug = ?, article_type = ?,
                main_topic = ?, access_level = ?, source_markdown = ?, summary_markdown = ?, summary_html = ?,
                summary_editor_document_json = ?, summary_model = ?, summary_updated_at = ?, manual_summary_html_backup = ?,
                layout_mode = ?, formatting_notes = ?,
                content_markdown = ?, plain_text_content = ?, excerpt = ?,
                primary_column_manual = ?, tag_suggestion_payload_json = ?, tag_payload_json = ?, removed_tag_payload_json = ?,
                final_html = ?, html_web = ?, html_wechat = ?, editor_document_json = ?, editor_source = ?, editor_updated_at = ?,
                manual_final_html_backup = ?, render_metadata_json = ?, publish_validation_json = ?,
                updated_at = ?
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
                current.get("summary_markdown") or None,
                current.get("summary_html"),
                current.get("summary_editor_document_json") or "{}",
                current.get("summary_model"),
                current.get("summary_updated_at"),
                current.get("manual_summary_html_backup"),
                current["layout_mode"],
                current.get("formatting_notes"),
                current.get("content_markdown"),
                current["plain_text_content"],
                current["excerpt"],
                int(bool(current.get("primary_column_manual"))),
                current["tag_suggestion_payload_json"],
                current["tag_payload_json"],
                current["removed_tag_payload_json"],
                current.get("final_html"),
                current.get("html_web"),
                current.get("html_wechat"),
                current.get("editor_document_json") or "{}",
                current.get("editor_source"),
                current.get("editor_updated_at"),
                current.get("manual_final_html_backup"),
                current.get("render_metadata_json") or "{}",
                current["publish_validation_json"],
                current["updated_at"],
                editorial_id,
            ),
        )
        if "selected_topic_ids" in payload:
            _replace_editorial_selected_topics(connection, editorial_id, payload.get("selected_topic_ids") or [])
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
        regenerate_summary = bool(
            not str(current.get("summary_html") or "").strip()
            or str(current.get("summary_model") or "").strip()
        )
        summary_markdown = _normalize_summary_markdown(current.get("summary_markdown") or "")
        summary_html = str(current.get("summary_html") or "").strip() or None
        summary_model = str(current.get("summary_model") or "").strip() or None
        summary_editor_document_json = current.get("summary_editor_document_json") or "{}"
        summary_updated_at = current.get("summary_updated_at")
        if regenerate_summary:
            summary_assets = _build_summary_editorial_assets(
                current.get("title") or "",
                content_markdown or source_markdown,
            )
            summary_markdown = summary_assets.get("summary_markdown") or ""
            summary_html = str(summary_assets.get("summary_html") or "").strip() or None
            summary_model = summary_assets.get("summary_model")
            summary_editor_document_json = json.dumps(
                _build_editor_document_payload(summary_html),
                ensure_ascii=False,
            ) if summary_html else "{}"
            summary_updated_at = timestamp if summary_html else None
        excerpt = _extract_excerpt(strip_markdown(summary_markdown) or plain_text_content, limit=180)
        preview_article = {
            "title": current.get("title") or "",
            "source_url": current.get("source_url"),
            "author": current.get("author") or "",
            "organization": current.get("organization") or "",
            "content_markdown": content_markdown,
            "excerpt": excerpt,
        }
        final_html, render_metadata = _render_editorial_preview(preview_article)
        tag_payload = _load_tag_payload(current.get("tag_payload_json"))
        validation_payload = _build_publish_validation(
            {
                "title": current.get("title"),
                "source_markdown": source_markdown,
                "content_markdown": content_markdown,
                "tags": tag_payload,
                "primary_column_slug": current.get("primary_column_slug"),
                "final_html": final_html,
            }
        )
        connection.execute(
            """
            UPDATE editorial_articles
            SET source_markdown = ?,
                summary_markdown = ?,
                summary_html = ?,
                summary_editor_document_json = ?,
                summary_model = ?,
                summary_updated_at = ?,
                layout_mode = ?,
                formatting_notes = ?,
                formatter_model = ?,
                last_formatted_at = ?,
                content_markdown = ?,
                plain_text_content = ?,
                excerpt = ?,
                final_html = ?,
                html_web = ?,
                html_wechat = ?,
                editor_document_json = ?,
                editor_source = ?,
                editor_updated_at = ?,
                manual_final_html_backup = ?,
                render_metadata_json = ?,
                publish_validation_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                source_markdown,
                summary_markdown or None,
                summary_html,
                summary_editor_document_json,
                summary_model,
                summary_updated_at,
                layout_mode,
                formatting_notes or None,
                formatted.get("model"),
                timestamp,
                content_markdown,
                plain_text_content,
                excerpt,
                final_html,
                final_html,
                final_html,
                json.dumps(_build_editor_document_payload(final_html), ensure_ascii=False),
                EDITOR_SOURCE_AI,
                timestamp,
                current.get("final_html") if str(current.get("final_html") or "").strip() else current.get("manual_final_html_backup"),
                json.dumps(render_metadata, ensure_ascii=False),
                json.dumps(validation_payload, ensure_ascii=False),
                timestamp,
                editorial_id,
            ),
        )
        connection.commit()
    return get_editorial_article(editorial_id)


def generate_editorial_summary(editorial_id: int) -> dict:
    with connection_scope() as connection:
        current = dict(_fetch_editorial_row(connection, editorial_id))
        source_text = str(
            current.get("content_markdown")
            or current.get("source_markdown")
            or current.get("plain_text_content")
            or ""
        ).strip()
        if not source_text:
            raise HTTPException(status_code=400, detail="Summary source content is empty")

        previous_summary_html = str(current.get("summary_html") or "").strip()
        summary_assets = _build_summary_editorial_assets(current.get("title") or "", source_text)
        summary_markdown = summary_assets.get("summary_markdown") or ""
        summary_html = str(summary_assets.get("summary_html") or "").strip()
        if not summary_html:
            raise HTTPException(status_code=502, detail="AI summary HTML is empty")

        timestamp = _now_iso()
        excerpt = _extract_excerpt(strip_markdown(summary_markdown) or current.get("plain_text_content") or "", limit=180)
        connection.execute(
            """
            UPDATE editorial_articles
            SET summary_markdown = ?,
                summary_html = ?,
                summary_editor_document_json = ?,
                summary_model = ?,
                summary_updated_at = ?,
                manual_summary_html_backup = ?,
                excerpt = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                summary_markdown,
                summary_html,
                json.dumps(_build_editor_document_payload(summary_html), ensure_ascii=False),
                summary_assets.get("summary_model"),
                timestamp,
                previous_summary_html if previous_summary_html and previous_summary_html != summary_html else current.get("manual_summary_html_backup"),
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
        signal_entries = _extract_editorial_signal_entries(
            row.get("title") or "",
            row.get("excerpt") or "",
            row.get("plain_text_content") or row.get("content_markdown") or "",
        )

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
                "org_text": "",
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

        ai_suggestion_tags = _dedupe_tags([*signal_entries, *heuristic_entries, *ai_entries])
        removed_tags = _load_tag_payload(row.get("removed_tag_payload_json"))
        selected_tags = _apply_removed_tags(ai_suggestion_tags, removed_tags)

        excerpt = row.get("excerpt") or ""
        ai_excerpt = str(ai_payload.get("excerpt") or "").strip()
        if ai_excerpt:
            excerpt = ai_excerpt[:180]

        article_type = row.get("article_type")
        ai_article_type = str(ai_payload.get("article_type") or "").strip()
        if ai_article_type:
            article_type = ai_article_type[:32]
        elif not article_type and len(ai_suggestion_tags) >= 5:
            article_type = "深度分析"

        main_topic = row.get("main_topic")
        ai_main_topic = str(ai_payload.get("main_topic") or "").strip()
        if ai_main_topic:
            main_topic = ai_main_topic[:48]
        elif not main_topic:
            fallback_topic = next((item["name"] for item in ai_suggestion_tags if item.get("category") == "topic"), "")
            main_topic = fallback_topic[:48] if fallback_topic else main_topic

        column_slug = row.get("primary_column_slug")
        ai_column_slug = str(ai_payload.get("column_slug") or "").strip()
        if ai_column_slug not in VALID_COLUMN_SLUGS:
            ai_column_slug = _infer_column_slug(
                {
                    "title": row.get("title"),
                    "article_type": article_type,
                    "main_topic": main_topic,
                    "organization": "",
                },
                ai_suggestion_tags,
            )
        if not bool(row.get("primary_column_manual")):
            column_slug = ai_column_slug
        column_slug = _normalize_column_slug(column_slug) or _normalize_column_slug(ai_column_slug) or "insights"

        validation_payload = _build_publish_validation(
            {
                "title": row.get("title"),
                "source_markdown": row.get("source_markdown"),
                "content_markdown": row.get("content_markdown"),
                "tags": selected_tags,
                "primary_column_slug": column_slug,
                "final_html": row.get("final_html") or row.get("html_web"),
            }
        )

        connection.execute(
            """
            UPDATE editorial_articles
            SET excerpt = ?, article_type = ?, main_topic = ?, primary_column_slug = ?,
                primary_column_ai_slug = ?, tag_suggestion_payload_json = ?, tag_payload_json = ?,
                removed_tag_payload_json = ?, publish_validation_json = ?, editor_updated_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                excerpt or _extract_excerpt(row.get("plain_text_content") or ""),
                article_type,
                main_topic,
                column_slug,
                ai_column_slug,
                json.dumps(ai_suggestion_tags, ensure_ascii=False),
                json.dumps(selected_tags, ensure_ascii=False),
                json.dumps(_compute_removed_tags(ai_suggestion_tags, selected_tags), ensure_ascii=False),
                json.dumps(validation_payload, ensure_ascii=False),
                _now_iso() if row.get("status") == "published" else row.get("editor_updated_at"),
                _now_iso(),
                editorial_id,
            ),
        )
        connection.commit()

    return get_editorial_article(editorial_id)


def render_editorial_html(editorial_id: int) -> dict:
    article = get_editorial_article(editorial_id)
    final_html, render_metadata = _render_editorial_preview(article)
    updated_at = _now_iso()
    validation_payload = _build_publish_validation(
        {
            "title": article.get("title"),
            "source_markdown": article.get("source_markdown"),
            "content_markdown": article.get("content_markdown"),
            "tags": article.get("tags") or [],
            "primary_column_slug": article.get("primary_column_slug"),
            "final_html": final_html,
        }
    )
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE editorial_articles
            SET final_html = ?, html_web = ?, html_wechat = ?, editor_document_json = ?, editor_source = ?, editor_updated_at = ?,
                render_metadata_json = ?, publish_validation_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                final_html,
                final_html,
                final_html,
                json.dumps(_build_editor_document_payload(final_html), ensure_ascii=False),
                EDITOR_SOURCE_AI,
                updated_at,
                json.dumps(render_metadata, ensure_ascii=False),
                json.dumps(validation_payload, ensure_ascii=False),
                updated_at,
                editorial_id,
            ),
        )
        connection.commit()

    return {
        "article_id": editorial_id,
        "final_html": final_html,
        "html_web": final_html,
        "html_wechat": final_html,
        "summary": article.get("excerpt") or "",
        "render_metadata": render_metadata,
    }


def export_editorial_html(editorial_id: int, variant: str) -> tuple[str, str]:
    del editorial_id, variant
    raise HTTPException(status_code=410, detail="Editorial HTML export has been removed from the workbench")


def publish_editorial_article(editorial_id: int) -> dict:
    article = get_editorial_article(editorial_id)
    validation_errors = _build_publish_validation(article)
    if validation_errors:
        with connection_scope() as connection:
            connection.execute(
                """
                UPDATE editorial_articles
                SET publish_validation_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(validation_errors, ensure_ascii=False), _now_iso(), editorial_id),
            )
            connection.commit()
        issue_text = "；".join(issue["message"] for issue in validation_errors)
        raise HTTPException(status_code=400, detail=f"发布前校验未通过：{issue_text}")

    now = _now_iso()
    with connection_scope() as connection:
        row = dict(_fetch_editorial_row(connection, editorial_id))
        selected_topics = _resolve_effective_editorial_topics(connection, row)
        summary_html = str(row.get("summary_html") or "").strip()
        published_summary_html = summary_html or _build_summary_editorial_html(row.get("summary_markdown") or row.get("excerpt") or "")
        excerpt = _extract_excerpt(
            strip_markdown(row.get("summary_markdown") or "") or row.get("plain_text_content") or "",
            limit=180,
        )
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
        source_url = row.get("source_url") or None

        # In editorial drafts, `organization` is used as editor credit in the render flow.
        # Publishing it into article organization fields pollutes organization pages and autotag signals.
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
                    excerpt,
                    row["main_topic"],
                    row["article_type"],
                    "内容后台",
                    None,
                    tag_text,
                    "",
                    f"{row['title']} {excerpt or ''} {plain_text[:4000]}",
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
                    excerpt,
                    row["main_topic"],
                    row["article_type"],
                    "内容后台",
                    None,
                    tag_text,
                    "",
                    f"{row['title']} {excerpt or ''} {plain_text[:4000]}",
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
        _sync_article_topics_from_editorial(connection, article_id, selected_topics)

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
                draft_box_state = ?,
                workflow_status = 'published',
                excerpt = ?,
                published_summary_html = ?,
                published_final_html = COALESCE(final_html, html_web, html_wechat),
                publish_validation_json = '[]',
                approved_at = COALESCE(approved_at, ?),
                published_at = COALESCE(published_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (article_id, public_slug, DRAFT_BOX_STATE_ARCHIVED, excerpt, published_summary_html, now, now, now, editorial_id),
        )
        connection.commit()

    refresh_search_cache()
    return {
        "editorial_id": editorial_id,
        "article_id": article_id,
        "status": "published",
        "article_url": f"/article/{article_id}",
        "updated_at": now,
        "selected_topics": selected_topics,
    }
