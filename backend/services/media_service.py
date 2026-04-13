from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile

from backend.config import MEDIA_UPLOADS_DIR
from backend.database import connection_scope
from backend.services import ai_service
from backend.services.html_renderer import strip_markdown
from backend.services.image_upload_service import save_image_upload
from backend.services.local_media_library import LOCAL_AUDIO_ITEMS
from backend.services.upload_text_service import extract_upload_content

VISIBILITY_LABELS = {
    "public": "公开",
    "member": "会员",
    "paid": "付费",
}
VALID_VISIBILITY = set(VISIBILITY_LABELS)
VALID_KINDS = {"audio", "video"}
VALID_STATUSES = {"draft", "published"}
VALID_UPLOAD_USAGES = {"media", "cover", "transcript", "script"}
VALID_DRAFT_BOX_STATES = {"active", "archived"}
VALID_WORKFLOW_STATUSES = {"draft", "published"}
MEDIA_PREVIEW_SECONDS = 60
ALLOWED_UPLOAD_EXTENSIONS = {
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg"},
    "video": {".mp4", ".mov", ".m4v", ".webm"},
}
ALLOWED_TEXT_UPLOAD_EXTENSIONS = {".md", ".txt", ".html", ".htm", ".docx"}
LEGACY_AUDIO_SEED_SLUGS = {
    "audio-ai-decision-lab",
    "audio-case-briefing-weekly",
    "audio-chairman-private-brief",
}
HUB_HIDDEN_SLUG_PREFIXES = ("round18-smoke-",)
DRAFT_BOX_STATE_ACTIVE = "active"
DRAFT_BOX_STATE_ARCHIVED = "archived"
UPLOAD_CHUNK_SIZE = 1024 * 1024
MEDIA_TIMESTAMP_LINE_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:\[\s*)?(?P<label>(?:\d{1,2}:)?\d{1,2}:\d{2})(?:\s*\])?\s*(?:[-—–|：:]\s*)?(?P<title>.+)$"
)


def datetime_now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _slugify(value: str) -> str:
    text = re.sub(r"[^\w\s-]", "", value.lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:80] or f"media-{date.today().isoformat()}"


def _normalize_kind(value: str | None) -> str:
    normalized = (value or "").strip()
    if normalized not in VALID_KINDS:
        raise HTTPException(status_code=404, detail="Media kind not found")
    return normalized


def _normalize_visibility(value: str | None) -> str:
    normalized = (value or "").strip() or "public"
    if normalized not in VALID_VISIBILITY:
        raise HTTPException(status_code=400, detail="Unsupported media visibility")
    return normalized


def _normalize_status(value: str | None) -> str:
    normalized = (value or "").strip() or "draft"
    if normalized not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported media status")
    return normalized


def _normalize_draft_box_state(value: str | None) -> str:
    normalized = (value or "").strip() or DRAFT_BOX_STATE_ACTIVE
    if normalized not in VALID_DRAFT_BOX_STATES:
        raise HTTPException(status_code=400, detail="Unsupported media draft-box state")
    return normalized


def _normalize_workflow_status(value: str | None) -> str:
    normalized = (value or "").strip() or "draft"
    if normalized not in VALID_WORKFLOW_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported media workflow status")
    return normalized


def _normalize_publish_date(value: str | None) -> str:
    if not value:
        return date.today().isoformat()
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid media publish date") from exc


def _normalize_episode_number(value: int | None) -> int:
    if value is None:
        return 1
    return max(1, int(value))


def _compact_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _apply_visibility_policy(kind: str, visibility: str | None) -> str:
    normalized = _normalize_visibility(visibility)
    if kind == "audio":
        return "paid"
    return normalized


def _extract_excerpt(value: str | None, limit: int = 160) -> str:
    compact = _compact_text(value)
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def _sanitize_filename(value: str) -> str:
    raw = Path(value or "media.bin").name
    stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", Path(raw).stem).strip("-")
    suffix = Path(raw).suffix.lower()
    return f"{stem[:80] or 'media'}{suffix}"


def _load_chapters(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []

    chapters: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        timestamp_label = str(item.get("timestamp_label") or "").strip()
        if not title or not timestamp_label:
            continue
        try:
            timestamp_seconds = max(0, int(item.get("timestamp_seconds") or 0))
        except (TypeError, ValueError):
            timestamp_seconds = 0
        chapters.append(
            {
                "title": title,
                "timestamp_label": timestamp_label,
                "timestamp_seconds": timestamp_seconds,
            }
        )
    return chapters


def _normalize_chapters(chapters: list[dict] | None) -> list[dict]:
    return _load_chapters(json.dumps(chapters or [], ensure_ascii=False))


def _timestamp_label_to_seconds(label: str) -> int:
    parts = [int(part) for part in label.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return max(0, minutes * 60 + seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return max(0, hours * 3600 + minutes * 60 + seconds)
    return 0


def _extract_media_chapters_from_text(text: str | None, *, limit: int = 8) -> list[dict]:
    chapters: list[dict] = []
    seen_labels: set[str] = set()
    for raw_line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        compact = _compact_text(strip_markdown(raw_line))
        if not compact:
            continue
        match = MEDIA_TIMESTAMP_LINE_RE.match(compact)
        if not match:
            continue
        label = match.group("label").strip()
        title = match.group("title").strip().strip("[]")
        if not title or label in seen_labels:
            continue
        seen_labels.add(label)
        chapters.append(
            {
                "title": title[:80],
                "timestamp_label": label,
                "timestamp_seconds": _timestamp_label_to_seconds(label),
            }
        )
        if len(chapters) >= limit:
            break
    return chapters


def _resolve_access(kind: str, visibility: str, membership: dict | None) -> tuple[bool, str | None]:
    visibility = _apply_visibility_policy(kind, visibility)
    if membership is None:
        return True, None
    preview_label = "试听" if kind == "audio" else "试看"
    full_action = "收听" if kind == "audio" else "观看"
    asset_label = "音频" if kind == "audio" else "视频"
    if visibility == "public":
        return True, None
    if visibility == "member":
        if membership["can_access_member"]:
            return True, None
        return False, f"当前{asset_label}可先{preview_label} {MEDIA_PREVIEW_SECONDS // 60} 分钟，登录成为免费会员后可{full_action}完整内容。"
    if visibility == "paid":
        if membership["can_access_paid"]:
            return True, None
        if membership["can_access_member"]:
            return False, f"当前{asset_label}可先{preview_label} {MEDIA_PREVIEW_SECONDS // 60} 分钟，升级为付费会员后可{full_action}完整版。"
        return False, f"当前{asset_label}可先{preview_label} {MEDIA_PREVIEW_SECONDS // 60} 分钟，登录并升级为付费会员后可{full_action}完整版。"
    return False, "内容权限配置异常。"


def _serialize_media_row(row, membership: dict | None = None) -> dict:
    chapters = _load_chapters(row["chapter_payload_json"])
    effective_visibility = _apply_visibility_policy(row["kind"], row["visibility"])
    accessible, gate_copy = _resolve_access(row["kind"], effective_visibility, membership)
    transcript_excerpt = _extract_excerpt(row["transcript_markdown"] or row["body_markdown"] or row["summary"])
    preview_url = row["preview_url"] or (row["media_url"] if not accessible else "")
    preview_duration_seconds = 0 if accessible else min(max(0, int(row["duration_seconds"] or 0)), MEDIA_PREVIEW_SECONDS)
    return {
        "id": row["id"],
        "media_item_id": row["id"],
        "slug": row["slug"],
        "kind": row["kind"],
        "title": row["title"],
        "summary": row["summary"],
        "speaker": row["speaker"],
        "series_name": row["series_name"],
        "episode_number": row["episode_number"],
        "publish_date": row["publish_date"],
        "duration_seconds": row["duration_seconds"],
        "visibility": effective_visibility,
        "visibility_label": VISIBILITY_LABELS.get(effective_visibility, effective_visibility),
        "status": row["status"],
        "workflow_status": "published" if row["status"] == "published" else "draft",
        "draft_box_state": DRAFT_BOX_STATE_ARCHIVED if row["status"] == "published" else DRAFT_BOX_STATE_ACTIVE,
        "accessible": accessible,
        "gate_copy": gate_copy,
        "cover_image_url": row["cover_image_url"],
        "media_url": row["media_url"] if accessible else None,
        "preview_url": preview_url,
        "preview_duration_seconds": preview_duration_seconds,
        "source_url": row["source_url"],
        "transcript_excerpt": transcript_excerpt,
        "chapter_count": len(chapters),
        "has_unpublished_changes": False,
        "is_reopened_from_published": False,
        "copy_model": None,
        "copy_updated_at": None,
        "manual_copy_updated_at": None,
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else None,
        "published_at": row["updated_at"] if "updated_at" in row.keys() else None,
        "transcript_markdown": row["transcript_markdown"] or "",
        "script_markdown": row["script_markdown"] if "script_markdown" in row.keys() else "",
        "body_markdown": row["body_markdown"] or "",
        "chapters": chapters,
        "published_summary": row["summary"],
        "published_body_markdown": row["body_markdown"] or "",
        "published_transcript_markdown": row["transcript_markdown"] or "",
        "published_script_markdown": row["script_markdown"] if "script_markdown" in row.keys() else "",
        "published_media_url": row["media_url"],
        "published_cover_image_url": row["cover_image_url"],
        "published_chapters": chapters,
    }


def _parse_published_payload(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _draft_track_payload(row: dict) -> dict[str, object]:
    return {
        "slug": str(row.get("slug") or "").strip(),
        "title": str(row.get("title") or "").strip(),
        "summary": str(row.get("summary") or "").strip(),
        "speaker": str(row.get("speaker") or "").strip(),
        "series_name": str(row.get("series_name") or "").strip(),
        "episode_number": int(row.get("episode_number") or 1),
        "publish_date": str(row.get("publish_date") or "").strip(),
        "duration_seconds": int(row.get("duration_seconds") or 0),
        "visibility": _apply_visibility_policy(str(row.get("kind") or "audio"), row.get("visibility")),
        "cover_image_url": str(row.get("cover_image_url") or "").strip(),
        "media_url": str(row.get("media_url") or "").strip(),
        "source_url": str(row.get("source_url") or "").strip(),
        "body_markdown": str(row.get("body_markdown") or "").strip(),
        "transcript_markdown": str(row.get("transcript_markdown") or "").strip(),
        "script_markdown": str(row.get("script_markdown") or "").strip(),
        "chapters": _load_chapters(row.get("chapter_payload_json")),
    }


def _published_track_payload_from_media_row(row) -> dict[str, object]:
    source = dict(row)
    return {
        "slug": str(source.get("slug") or "").strip(),
        "title": str(source.get("title") or "").strip(),
        "summary": str(source.get("summary") or "").strip(),
        "speaker": str(source.get("speaker") or "").strip(),
        "series_name": str(source.get("series_name") or "").strip(),
        "episode_number": int(source.get("episode_number") or 1),
        "publish_date": str(source.get("publish_date") or "").strip(),
        "duration_seconds": int(source.get("duration_seconds") or 0),
        "visibility": _apply_visibility_policy(str(source.get("kind") or "audio"), source.get("visibility")),
        "cover_image_url": str(source.get("cover_image_url") or "").strip(),
        "media_url": str(source.get("media_url") or "").strip(),
        "source_url": str(source.get("source_url") or "").strip(),
        "body_markdown": str(source.get("body_markdown") or "").strip(),
        "transcript_markdown": str(source.get("transcript_markdown") or "").strip(),
        "script_markdown": str(source.get("script_markdown") or "").strip(),
        "chapters": _load_chapters(source.get("chapter_payload_json")),
    }


def _serialize_media_draft_row(row) -> dict:
    current = dict(row)
    chapters = _load_chapters(current.get("chapter_payload_json"))
    published_payload = _parse_published_payload(current.get("published_payload_json"))
    current_payload = _draft_track_payload(current)
    has_unpublished_changes = bool(
        published_payload
        and json.dumps(current_payload, ensure_ascii=False, sort_keys=True) != json.dumps(published_payload, ensure_ascii=False, sort_keys=True)
    )
    effective_visibility = _apply_visibility_policy(current["kind"], current.get("visibility"))
    published_chapters = _load_chapters(json.dumps(published_payload.get("chapters") or [], ensure_ascii=False))
    transcript_excerpt = _extract_excerpt(
        current.get("transcript_markdown") or current.get("script_markdown") or current.get("body_markdown") or current.get("summary")
    )
    return {
        "id": current["id"],
        "media_item_id": current.get("media_item_id"),
        "slug": current["slug"],
        "kind": current["kind"],
        "title": current.get("title") or "",
        "summary": current.get("summary") or "",
        "speaker": current.get("speaker"),
        "series_name": current.get("series_name"),
        "episode_number": current.get("episode_number") or 1,
        "publish_date": current.get("publish_date") or date.today().isoformat(),
        "duration_seconds": current.get("duration_seconds") or 0,
        "visibility": effective_visibility,
        "visibility_label": VISIBILITY_LABELS.get(effective_visibility, effective_visibility),
        "status": current.get("status") or "draft",
        "workflow_status": _normalize_workflow_status(current.get("workflow_status")),
        "draft_box_state": _normalize_draft_box_state(current.get("draft_box_state")),
        "accessible": True,
        "gate_copy": None,
        "cover_image_url": current.get("cover_image_url"),
        "media_url": current.get("media_url"),
        "preview_url": current.get("media_url"),
        "preview_duration_seconds": 0,
        "source_url": current.get("source_url"),
        "transcript_excerpt": transcript_excerpt,
        "chapter_count": len(chapters),
        "has_unpublished_changes": has_unpublished_changes,
        "is_reopened_from_published": bool(current.get("media_item_id") and published_payload),
        "copy_model": str(current.get("copy_model") or "").strip() or None,
        "copy_updated_at": current.get("copy_updated_at"),
        "manual_copy_updated_at": current.get("manual_copy_updated_at"),
        "updated_at": current.get("updated_at"),
        "published_at": current.get("published_at"),
        "transcript_markdown": current.get("transcript_markdown") or "",
        "script_markdown": current.get("script_markdown") or "",
        "body_markdown": current.get("body_markdown") or "",
        "chapters": chapters,
        "published_summary": str(published_payload.get("summary") or "").strip() or None,
        "published_body_markdown": str(published_payload.get("body_markdown") or "").strip() or None,
        "published_transcript_markdown": str(published_payload.get("transcript_markdown") or "").strip() or None,
        "published_script_markdown": str(published_payload.get("script_markdown") or "").strip() or None,
        "published_media_url": str(published_payload.get("media_url") or "").strip() or None,
        "published_cover_image_url": str(published_payload.get("cover_image_url") or "").strip() or None,
        "published_chapters": published_chapters,
    }


def _unique_slug(connection, table_name: str, base_slug: str, *, exclude_id: int | None = None) -> str:
    candidate = base_slug or f"media-{date.today().isoformat()}"
    suffix = 1
    while True:
        row = connection.execute(f"SELECT id FROM {table_name} WHERE slug = ?", (candidate,)).fetchone()
        if row is None or (exclude_id is not None and row["id"] == exclude_id):
            return candidate
        candidate = f"{base_slug[:72]}-{suffix}"
        suffix += 1


def _fetch_media_draft_row(connection, media_id: int):
    row = connection.execute("SELECT * FROM media_drafts WHERE id = ?", (media_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Media draft not found")
    return row


def _fetch_published_media_row(connection, media_item_id: int):
    row = connection.execute("SELECT * FROM media_items WHERE id = ?", (media_item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Published media item not found")
    return row


def _default_draft_title(kind: str) -> str:
    return "未命名音频草稿" if kind == "audio" else "未命名视频草稿"


def _normalize_media_draft_input(payload: dict, current: dict | None = None) -> dict:
    current_payload = current or {}
    kind = _normalize_kind(payload.get("kind") if payload.get("kind") is not None else current_payload.get("kind"))
    title = _compact_text(payload.get("title")) if payload.get("title") is not None else _compact_text(current_payload.get("title"))
    summary = _compact_text(payload.get("summary")) if payload.get("summary") is not None else _compact_text(current_payload.get("summary"))
    speaker = _compact_text(payload.get("speaker")) if "speaker" in payload else _compact_text(current_payload.get("speaker"))
    series_name = _compact_text(payload.get("series_name")) if "series_name" in payload else _compact_text(current_payload.get("series_name"))
    publish_date = _normalize_publish_date(payload.get("publish_date") if "publish_date" in payload else current_payload.get("publish_date"))
    duration_seconds = max(0, int(payload.get("duration_seconds") if payload.get("duration_seconds") is not None else current_payload.get("duration_seconds") or 0))
    visibility = _apply_visibility_policy(kind, payload.get("visibility") if payload.get("visibility") is not None else current_payload.get("visibility"))
    status = _normalize_status(payload.get("status") if payload.get("status") is not None else current_payload.get("status"))
    cover_image_url = _compact_text(payload.get("cover_image_url")) if "cover_image_url" in payload else _compact_text(current_payload.get("cover_image_url"))
    media_url = _compact_text(payload.get("media_url")) if "media_url" in payload else _compact_text(current_payload.get("media_url"))
    source_url = _compact_text(payload.get("source_url")) if "source_url" in payload else _compact_text(current_payload.get("source_url"))
    body_markdown = str(payload.get("body_markdown") if "body_markdown" in payload else current_payload.get("body_markdown") or "").strip()
    transcript_markdown = str(payload.get("transcript_markdown") if "transcript_markdown" in payload else current_payload.get("transcript_markdown") or "").strip()
    script_markdown = str(payload.get("script_markdown") if "script_markdown" in payload else current_payload.get("script_markdown") or "").strip()
    chapters = _normalize_chapters(payload.get("chapters")) if "chapters" in payload else _load_chapters(current_payload.get("chapter_payload_json"))
    return {
        "kind": kind,
        "title": title or current_payload.get("title") or _default_draft_title(kind),
        "summary": summary or current_payload.get("summary") or "",
        "speaker": speaker or None,
        "series_name": series_name or None,
        "episode_number": _normalize_episode_number(payload.get("episode_number") if payload.get("episode_number") is not None else current_payload.get("episode_number")),
        "publish_date": publish_date,
        "duration_seconds": duration_seconds,
        "visibility": visibility,
        "status": status,
        "cover_image_url": cover_image_url or None,
        "media_url": media_url or None,
        "source_url": source_url or None,
        "body_markdown": body_markdown,
        "transcript_markdown": transcript_markdown,
        "script_markdown": script_markdown,
        "chapters": chapters,
    }


def list_media_items(kind: str, membership: dict, limit: int = 24) -> dict:
    sync_local_audio_library()
    normalized_kind = _normalize_kind(kind)
    safe_limit = max(1, min(limit, 60))
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                slug,
                kind,
                title,
                summary,
                speaker,
                series_name,
                episode_number,
                publish_date,
                duration_seconds,
                visibility,
                status,
                cover_image_url,
                media_url,
                preview_url,
                source_url,
                body_markdown,
                transcript_markdown,
                script_markdown,
                chapter_payload_json,
                updated_at
            FROM media_items
            WHERE kind = ? AND status = 'published'
              AND slug NOT LIKE 'round18-smoke-%'
            ORDER BY publish_date DESC, id DESC, sort_order ASC, episode_number DESC
            LIMIT ?
            """,
            (normalized_kind, safe_limit),
        ).fetchall()
        count_rows = connection.execute(
            """
            SELECT visibility, COUNT(*) AS total
            FROM media_items
            WHERE kind = ? AND status = 'published'
              AND slug NOT LIKE 'round18-smoke-%'
            GROUP BY visibility
            """,
            (normalized_kind,),
        ).fetchall()

    items = [_serialize_media_row(row, membership) for row in rows]
    counts = {row["visibility"]: row["total"] for row in count_rows}
    return {
        "kind": normalized_kind,
        "viewer_tier": membership["tier"],
        "total": len(items),
        "public_count": counts.get("public", 0),
        "member_count": counts.get("member", 0),
        "paid_count": counts.get("paid", 0),
        "items": items,
    }


def list_admin_media_items(
    kind: str | None = None,
    status: str | None = None,
    limit: int = 60,
    workflow_status: str | None = None,
    draft_box_state: str | None = DRAFT_BOX_STATE_ACTIVE,
) -> dict:
    sync_local_audio_library()
    safe_limit = max(1, min(limit, 100))
    filters: list[str] = []
    params: list[object] = []
    if kind:
        filters.append("kind = ?")
        params.append(_normalize_kind(kind))
    if status:
        filters.append("status = ?")
        params.append(_normalize_status(status))
    if workflow_status:
        filters.append("workflow_status = ?")
        params.append(_normalize_workflow_status(workflow_status))
    if draft_box_state and str(draft_box_state).strip() != "all":
        filters.append("draft_box_state = ?")
        params.append(_normalize_draft_box_state(draft_box_state))
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    with connection_scope() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM media_drafts
            {where_sql}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (*params, safe_limit),
        ).fetchall()
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM media_drafts
            {where_sql}
            """,
            params,
        ).fetchone()["total"]

    return {
        "items": [_serialize_media_draft_row(row) for row in rows],
        "total": total,
    }


def list_admin_media_source_items(kind: str | None = None, query: str = "", limit: int = 24) -> dict:
    sync_local_audio_library()
    safe_limit = max(1, min(limit, 60))
    filters = ["status = 'published'"]
    params: list[object] = []
    if kind:
        filters.append("kind = ?")
        params.append(_normalize_kind(kind))
    if query.strip():
        term = f"%{query.strip()}%"
        filters.append("(title LIKE ? OR summary LIKE ? OR speaker LIKE ? OR series_name LIKE ?)")
        params.extend([term, term, term, term])
    where_sql = f"WHERE {' AND '.join(filters)}"
    with connection_scope() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM media_items
            {where_sql}
            ORDER BY publish_date DESC, id DESC
            LIMIT ?
            """,
            (*params, safe_limit),
        ).fetchall()
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM media_items
            {where_sql}
            """,
            params,
        ).fetchone()["total"]
    return {
        "items": [_serialize_media_row(row, membership=None) for row in rows],
        "total": total,
    }


def get_admin_media_item(media_id: int) -> dict:
    sync_local_audio_library()
    with connection_scope() as connection:
        row = _fetch_media_draft_row(connection, media_id)
    return _serialize_media_draft_row(row)


def _persist_media_draft(connection, media_id: int | None, payload: dict, current: dict | None = None) -> int:
    normalized = _normalize_media_draft_input(payload, current)
    timestamp = datetime_now_iso()
    base_slug = _slugify(payload.get("slug") or normalized["title"])
    if media_id is None:
        draft_slug = _unique_slug(connection, "media_drafts", base_slug)
        connection.execute(
            """
            INSERT INTO media_drafts (
                media_item_id,
                slug,
                kind,
                title,
                summary,
                speaker,
                series_name,
                episode_number,
                publish_date,
                duration_seconds,
                visibility,
                status,
                draft_box_state,
                workflow_status,
                cover_image_url,
                media_url,
                source_url,
                body_markdown,
                transcript_markdown,
                script_markdown,
                chapter_payload_json,
                published_payload_json,
                created_at,
                updated_at,
                published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?)
            """,
            (
                current.get("media_item_id") if current else None,
                draft_slug,
                normalized["kind"],
                normalized["title"],
                normalized["summary"],
                normalized["speaker"],
                normalized["series_name"],
                normalized["episode_number"],
                normalized["publish_date"],
                normalized["duration_seconds"],
                normalized["visibility"],
                normalized["status"],
                _normalize_draft_box_state((current or {}).get("draft_box_state")),
                _normalize_workflow_status((current or {}).get("workflow_status")),
                normalized["cover_image_url"],
                normalized["media_url"],
                normalized["source_url"],
                normalized["body_markdown"],
                normalized["transcript_markdown"],
                normalized["script_markdown"],
                json.dumps(normalized["chapters"], ensure_ascii=False),
                (current or {}).get("created_at") or timestamp,
                timestamp,
                (current or {}).get("published_at"),
            ),
        )
        return int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])

    current_row = current or dict(_fetch_media_draft_row(connection, media_id))
    draft_slug = current_row["slug"]
    if payload.get("slug") is not None:
        draft_slug = _unique_slug(connection, "media_drafts", base_slug, exclude_id=media_id)
    manual_copy_updated_at = current_row.get("manual_copy_updated_at")
    if any(field in payload for field in {"summary", "body_markdown", "transcript_markdown", "script_markdown", "chapters"}):
        manual_copy_updated_at = timestamp
    connection.execute(
        """
        UPDATE media_drafts
        SET slug = ?,
            kind = ?,
            title = ?,
            summary = ?,
            speaker = ?,
            series_name = ?,
            episode_number = ?,
            publish_date = ?,
            duration_seconds = ?,
            visibility = ?,
            status = ?,
            cover_image_url = ?,
            media_url = ?,
            source_url = ?,
            body_markdown = ?,
            transcript_markdown = ?,
            script_markdown = ?,
            chapter_payload_json = ?,
            manual_copy_updated_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            draft_slug,
            normalized["kind"],
            normalized["title"],
            normalized["summary"],
            normalized["speaker"],
            normalized["series_name"],
            normalized["episode_number"],
            normalized["publish_date"],
            normalized["duration_seconds"],
            normalized["visibility"],
            normalized["status"],
            normalized["cover_image_url"],
            normalized["media_url"],
            normalized["source_url"],
            normalized["body_markdown"],
            normalized["transcript_markdown"],
            normalized["script_markdown"],
            json.dumps(normalized["chapters"], ensure_ascii=False),
            manual_copy_updated_at,
            timestamp,
            media_id,
        ),
    )
    return media_id


def create_media_item(payload: dict) -> dict:
    sync_local_audio_library()
    kind = _normalize_kind(payload.get("kind"))
    with connection_scope() as connection:
        media_id = _persist_media_draft(
            connection,
            None,
            {
                **payload,
                "kind": kind,
                "publish_date": payload.get("publish_date") or date.today().isoformat(),
                "status": payload.get("status") or "draft",
            },
            current={
                "draft_box_state": DRAFT_BOX_STATE_ACTIVE,
                "workflow_status": "draft",
            },
        )
        connection.commit()
    if _normalize_status(payload.get("status")) == "published":
        return publish_media_item(media_id)
    return get_admin_media_item(media_id)


def update_media_item(media_id: int, payload: dict) -> dict:
    sync_local_audio_library()
    with connection_scope() as connection:
        current = dict(_fetch_media_draft_row(connection, media_id))
        _persist_media_draft(connection, media_id, payload, current=current)
        connection.commit()
    if payload.get("status") is not None and _normalize_status(payload.get("status")) == "published":
        return publish_media_item(media_id)
    return get_admin_media_item(media_id)


def delete_media_item(media_id: int) -> dict:
    with connection_scope() as connection:
        row = dict(_fetch_media_draft_row(connection, media_id))
        linked_media_id = row.get("media_item_id")
        if linked_media_id:
            linked_row = connection.execute("SELECT status FROM media_items WHERE id = ?", (linked_media_id,)).fetchone()
            if linked_row is not None and linked_row["status"] != "published":
                connection.execute("DELETE FROM media_items WHERE id = ?", (linked_media_id,))
        connection.execute("DELETE FROM media_drafts WHERE id = ?", (media_id,))
        connection.commit()
    return {"media_id": media_id, "deleted": True}


def generate_media_copy(media_id: int) -> dict:
    with connection_scope() as connection:
        current = dict(_fetch_media_draft_row(connection, media_id))
        source_text = str(current.get("script_markdown") or current.get("transcript_markdown") or "").strip()
        if not source_text:
            raise HTTPException(status_code=400, detail="Please upload a transcript or script before generating copy")
        generated = ai_service.generate_media_text_assets(
            title=current.get("title") or "",
            kind=current.get("kind") or "audio",
            speaker=current.get("speaker") or "",
            series_name=current.get("series_name") or "",
            transcript_markdown=current.get("transcript_markdown") or "",
            script_markdown=current.get("script_markdown") or "",
        )
        chapters = _load_chapters(current.get("chapter_payload_json"))
        if not chapters:
            chapters = _extract_media_chapters_from_text(source_text)
        timestamp = datetime_now_iso()
        connection.execute(
            """
            UPDATE media_drafts
            SET summary = ?,
                body_markdown = ?,
                chapter_payload_json = ?,
                copy_model = ?,
                copy_updated_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                _compact_text(generated.get("summary")),
                str(generated.get("body_markdown") or "").strip(),
                json.dumps(chapters, ensure_ascii=False),
                str(generated.get("model") or "").strip() or None,
                timestamp,
                timestamp,
                media_id,
            ),
        )
        connection.commit()
    return get_admin_media_item(media_id)


def _build_publish_ready_draft(current: dict) -> dict:
    payload = dict(current)
    summary = _compact_text(payload.get("summary"))
    body_markdown = str(payload.get("body_markdown") or "").strip()
    source_text = str(payload.get("script_markdown") or payload.get("transcript_markdown") or "").strip()
    if source_text and (not summary or not body_markdown):
        generated = ai_service.generate_media_text_assets(
            title=payload.get("title") or "",
            kind=payload.get("kind") or "audio",
            speaker=payload.get("speaker") or "",
            series_name=payload.get("series_name") or "",
            transcript_markdown=payload.get("transcript_markdown") or "",
            script_markdown=payload.get("script_markdown") or "",
        )
        summary = summary or _compact_text(generated.get("summary"))
        body_markdown = body_markdown or str(generated.get("body_markdown") or "").strip()
        payload["copy_model"] = str(generated.get("model") or "").strip() or None
        payload["copy_updated_at"] = datetime_now_iso()
    payload["summary"] = summary
    payload["body_markdown"] = body_markdown
    if not _load_chapters(payload.get("chapter_payload_json")) and source_text:
        payload["chapter_payload_json"] = json.dumps(_extract_media_chapters_from_text(source_text), ensure_ascii=False)
    return payload


def _validate_media_publish(payload: dict) -> None:
    if not str(payload.get("title") or "").strip():
        raise HTTPException(status_code=400, detail="Media title is required before publishing")
    if not str(payload.get("media_url") or "").strip():
        raise HTTPException(status_code=400, detail="Primary media file is required before publishing")
    if not str(payload.get("summary") or "").strip():
        raise HTTPException(status_code=400, detail="Media summary is required before publishing")
    if not str(payload.get("body_markdown") or "").strip():
        raise HTTPException(status_code=400, detail="Program description is required before publishing")


def _upsert_published_media_item(connection, payload: dict) -> int:
    current_media_id = payload.get("media_item_id")
    desired_slug = _slugify(payload.get("slug") or payload.get("title") or _default_draft_title(payload.get("kind") or "audio"))
    public_slug = _unique_slug(connection, "media_items", desired_slug, exclude_id=current_media_id)
    timestamp = datetime_now_iso()
    chapters_json = payload.get("chapter_payload_json") or "[]"
    source_url = _compact_text(payload.get("source_url") or payload.get("media_url"))
    if current_media_id and connection.execute("SELECT id FROM media_items WHERE id = ?", (current_media_id,)).fetchone():
        connection.execute(
            """
            UPDATE media_items
            SET slug = ?,
                kind = ?,
                title = ?,
                summary = ?,
                speaker = ?,
                series_name = ?,
                episode_number = ?,
                publish_date = ?,
                duration_seconds = ?,
                visibility = ?,
                status = 'published',
                cover_image_url = ?,
                media_url = ?,
                preview_url = COALESCE(NULLIF(preview_url, ''), ?),
                source_url = ?,
                body_markdown = ?,
                transcript_markdown = ?,
                script_markdown = ?,
                chapter_payload_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                public_slug,
                payload["kind"],
                payload["title"],
                payload["summary"],
                payload.get("speaker"),
                payload.get("series_name"),
                payload.get("episode_number") or 1,
                payload["publish_date"],
                payload.get("duration_seconds") or 0,
                _apply_visibility_policy(payload["kind"], payload.get("visibility")),
                payload.get("cover_image_url"),
                payload.get("media_url"),
                payload.get("media_url"),
                source_url,
                payload.get("body_markdown") or "",
                payload.get("transcript_markdown") or "",
                payload.get("script_markdown") or "",
                chapters_json,
                timestamp,
                current_media_id,
            ),
        )
        return int(current_media_id)

    connection.execute(
        """
        INSERT INTO media_items (
            slug,
            kind,
            title,
            summary,
            speaker,
            series_name,
            episode_number,
            publish_date,
            duration_seconds,
            visibility,
            status,
            cover_image_url,
            media_url,
            preview_url,
            source_url,
            body_markdown,
            transcript_markdown,
            script_markdown,
            chapter_payload_json,
            sort_order,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            public_slug,
            payload["kind"],
            payload["title"],
            payload["summary"],
            payload.get("speaker"),
            payload.get("series_name"),
            payload.get("episode_number") or 1,
            payload["publish_date"],
            payload.get("duration_seconds") or 0,
            _apply_visibility_policy(payload["kind"], payload.get("visibility")),
            payload.get("cover_image_url"),
            payload.get("media_url"),
            payload.get("media_url"),
            source_url,
            payload.get("body_markdown") or "",
            payload.get("transcript_markdown") or "",
            payload.get("script_markdown") or "",
            chapters_json,
            timestamp,
            timestamp,
        ),
    )
    return int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])


def publish_media_item(media_id: int) -> dict:
    with connection_scope() as connection:
        current = dict(_fetch_media_draft_row(connection, media_id))
        publish_ready = _build_publish_ready_draft(current)
        _validate_media_publish(publish_ready)
        media_item_id = _upsert_published_media_item(connection, {**current, **publish_ready})
        published_row = _fetch_published_media_row(connection, media_item_id)
        connection.execute("DELETE FROM media_drafts WHERE id = ?", (media_id,))
        connection.commit()
    return _serialize_media_row(published_row, membership=None)


def reopen_published_media_to_draft_box(media_item_id: int) -> dict:
    with connection_scope() as connection:
        source_row = _fetch_published_media_row(connection, media_item_id)
        if source_row["status"] != "published":
            raise HTTPException(status_code=400, detail="Only published media items can be reopened")
        published_payload = _published_track_payload_from_media_row(source_row)
        published_payload_json = json.dumps(published_payload, ensure_ascii=False)
        existing = connection.execute(
            """
            SELECT *
            FROM media_drafts
            WHERE media_item_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (media_item_id,),
        ).fetchone()
        timestamp = datetime_now_iso()
        if existing is not None:
            current = dict(existing)
            if _normalize_draft_box_state(current.get("draft_box_state")) == DRAFT_BOX_STATE_ACTIVE:
                return _serialize_media_draft_row(existing)
            connection.execute(
                """
                UPDATE media_drafts
                SET slug = ?,
                    kind = ?,
                    title = ?,
                    summary = ?,
                    speaker = ?,
                    series_name = ?,
                    episode_number = ?,
                    publish_date = ?,
                    duration_seconds = ?,
                    visibility = ?,
                    cover_image_url = ?,
                    media_url = ?,
                    source_url = ?,
                    body_markdown = ?,
                    transcript_markdown = ?,
                    script_markdown = ?,
                    chapter_payload_json = ?,
                    status = 'draft',
                    draft_box_state = ?,
                    workflow_status = 'draft',
                    published_payload_json = ?,
                    published_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    source_row["slug"],
                    source_row["kind"],
                    source_row["title"],
                    source_row["summary"],
                    source_row["speaker"],
                    source_row["series_name"],
                    source_row["episode_number"],
                    source_row["publish_date"],
                    source_row["duration_seconds"],
                    _apply_visibility_policy(source_row["kind"], source_row["visibility"]),
                    source_row["cover_image_url"],
                    source_row["media_url"],
                    source_row["source_url"],
                    source_row["body_markdown"],
                    source_row["transcript_markdown"],
                    source_row["script_markdown"] if "script_markdown" in source_row.keys() else "",
                    source_row["chapter_payload_json"],
                    DRAFT_BOX_STATE_ACTIVE,
                    published_payload_json,
                    source_row["updated_at"] if "updated_at" in source_row.keys() else timestamp,
                    timestamp,
                    current["id"],
                ),
            )
            connection.commit()
            return get_admin_media_item(int(current["id"]))

        draft_slug = _unique_slug(connection, "media_drafts", source_row["slug"])
        connection.execute(
            """
            INSERT INTO media_drafts (
                media_item_id,
                slug,
                kind,
                title,
                summary,
                speaker,
                series_name,
                episode_number,
                publish_date,
                duration_seconds,
                visibility,
                status,
                draft_box_state,
                workflow_status,
                cover_image_url,
                media_url,
                source_url,
                body_markdown,
                transcript_markdown,
                script_markdown,
                chapter_payload_json,
                published_payload_json,
                created_at,
                updated_at,
                published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                media_item_id,
                draft_slug,
                source_row["kind"],
                source_row["title"],
                source_row["summary"],
                source_row["speaker"],
                source_row["series_name"],
                source_row["episode_number"],
                source_row["publish_date"],
                source_row["duration_seconds"],
                _apply_visibility_policy(source_row["kind"], source_row["visibility"]),
                DRAFT_BOX_STATE_ACTIVE,
                source_row["cover_image_url"],
                source_row["media_url"],
                source_row["source_url"],
                source_row["body_markdown"],
                source_row["transcript_markdown"],
                source_row["script_markdown"] if "script_markdown" in source_row.keys() else "",
                source_row["chapter_payload_json"],
                published_payload_json,
                timestamp,
                timestamp,
                source_row["updated_at"] if "updated_at" in source_row.keys() else timestamp,
            ),
        )
        draft_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.commit()
    return get_admin_media_item(draft_id)


async def _write_upload_stream(upload: UploadFile, target_path: Path) -> int:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    await upload.seek(0)
    with target_path.open("wb") as handle:
        while True:
            chunk = await upload.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            handle.write(chunk)
            total_bytes += len(chunk)
    await upload.seek(0)
    return total_bytes


async def upload_media_asset(
    *,
    kind: str,
    usage: str,
    upload_file: UploadFile,
    filename: str,
    content_type: str | None = None,
    draft_id: int | None = None,
    duration_seconds: int | None = None,
) -> dict:
    normalized_kind = _normalize_kind(kind)
    normalized_usage = (usage or "").strip() or "media"
    if normalized_usage not in VALID_UPLOAD_USAGES:
        raise HTTPException(status_code=400, detail="Unsupported media upload usage")

    safe_name = _sanitize_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    target_dir = MEDIA_UPLOADS_DIR / normalized_kind / normalized_usage
    target_dir.mkdir(parents=True, exist_ok=True)
    base_stem = Path(safe_name).stem[:80] or normalized_kind
    timestamp = datetime_now_iso().replace(":", "-")

    if normalized_usage == "media":
        if suffix not in ALLOWED_UPLOAD_EXTENSIONS[normalized_kind]:
            raise HTTPException(status_code=400, detail="Unsupported media file type")
        final_name = f"{timestamp}-{base_stem}{suffix}"
        target_path = target_dir / final_name
        size_bytes = await _write_upload_stream(upload_file, target_path)
        relative_url = f"/media-uploads/{normalized_kind}/{normalized_usage}/{quote(final_name)}"
        detected_duration = max(0, int(duration_seconds or 0))
        inferred_title = _compact_text(re.sub(r"[-_]+", " ", Path(safe_name).stem))

        with connection_scope() as connection:
            current = dict(_fetch_media_draft_row(connection, draft_id)) if draft_id else None
            payload = {
                "kind": normalized_kind,
                "media_url": relative_url,
                "source_url": relative_url if not current or not str(current.get("source_url") or "").strip() else current.get("source_url"),
                "duration_seconds": detected_duration or int((current or {}).get("duration_seconds") or 0),
            }
            if not current or not _compact_text(current.get("title")) or _compact_text(current.get("title")) == _default_draft_title(normalized_kind):
                payload["title"] = inferred_title or _default_draft_title(normalized_kind)
            if current:
                media_id = _persist_media_draft(connection, draft_id, payload, current=current)
            else:
                media_id = _persist_media_draft(
                    connection,
                    None,
                    {
                        **payload,
                        "publish_date": date.today().isoformat(),
                        "status": "draft",
                    },
                    current={
                        "draft_box_state": DRAFT_BOX_STATE_ACTIVE,
                        "workflow_status": "draft",
                    },
                )
            connection.commit()
        return {
            "kind": normalized_kind,
            "usage": normalized_usage,
            "filename": final_name,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "url": relative_url,
            "item": get_admin_media_item(media_id),
        }

    if normalized_usage == "cover":
        saved = await save_image_upload(
            upload_file=upload_file,
            target_dir=target_dir,
            filename=filename,
            content_type=content_type,
        )
        relative_url = f"/media-uploads/{normalized_kind}/{normalized_usage}/{quote(saved['filename'])}"
        with connection_scope() as connection:
            current = dict(_fetch_media_draft_row(connection, draft_id)) if draft_id else None
            payload = {
                "kind": normalized_kind,
                "cover_image_url": relative_url,
            }
            if current:
                media_id = _persist_media_draft(connection, draft_id, payload, current=current)
            else:
                media_id = _persist_media_draft(
                    connection,
                    None,
                    {
                        **payload,
                        "publish_date": date.today().isoformat(),
                        "status": "draft",
                    },
                    current={
                        "draft_box_state": DRAFT_BOX_STATE_ACTIVE,
                        "workflow_status": "draft",
                    },
                )
            connection.commit()

        return {
            "kind": normalized_kind,
            "usage": normalized_usage,
            "filename": saved["filename"],
            "content_type": content_type,
            "size_bytes": saved["size_bytes"],
            "url": relative_url,
            "item": get_admin_media_item(media_id),
        }

    if suffix not in ALLOWED_TEXT_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported transcript or script file type")

    raw_bytes = await upload_file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded text file is empty")
    final_name = f"{timestamp}-{base_stem}{suffix}"
    target_path = target_dir / final_name
    target_path.write_bytes(raw_bytes)
    relative_url = f"/media-uploads/{normalized_kind}/{normalized_usage}/{quote(final_name)}"
    extracted_text = extract_upload_content(safe_name, raw_bytes).strip()
    if not extracted_text:
        raise HTTPException(status_code=400, detail="Unable to extract transcript or script text from the uploaded file")

    inferred_title = _compact_text(re.sub(r"[-_]+", " ", Path(safe_name).stem))
    field_name = "transcript_markdown" if normalized_usage == "transcript" else "script_markdown"
    with connection_scope() as connection:
        current = dict(_fetch_media_draft_row(connection, draft_id)) if draft_id else None
        payload = {
            "kind": normalized_kind,
            field_name: extracted_text,
        }
        if not current or not _compact_text(current.get("title")) or _compact_text(current.get("title")) == _default_draft_title(normalized_kind):
            payload["title"] = inferred_title or _default_draft_title(normalized_kind)
        if current:
            media_id = _persist_media_draft(connection, draft_id, payload, current=current)
        else:
            media_id = _persist_media_draft(
                connection,
                None,
                {
                    **payload,
                    "publish_date": date.today().isoformat(),
                    "status": "draft",
                },
                current={
                    "draft_box_state": DRAFT_BOX_STATE_ACTIVE,
                    "workflow_status": "draft",
                },
            )
        connection.commit()

    return {
        "kind": normalized_kind,
        "usage": normalized_usage,
        "filename": final_name,
        "content_type": content_type,
        "size_bytes": len(raw_bytes),
        "url": relative_url,
        "item": get_admin_media_item(media_id),
    }


def sync_local_audio_library() -> None:
    audio_directory = Path(__file__).resolve().parent.parent.parent / "audio"
    if not audio_directory.exists():
        return

    with connection_scope() as connection:
        connection.execute(
            """
            DELETE FROM media_items
            WHERE slug IN ({placeholders})
              AND kind = 'audio'
              AND COALESCE(media_url, '') = ''
            """.format(placeholders=",".join("?" for _ in LEGACY_AUDIO_SEED_SLUGS)),
            tuple(LEGACY_AUDIO_SEED_SLUGS),
        )

        for index, item in enumerate(LOCAL_AUDIO_ITEMS, start=1):
            file_path = audio_directory / item["file_name"]
            if not file_path.exists():
                continue
            media_url = f"/audio-files/{quote(item['file_name'])}"
            existing = connection.execute(
                "SELECT id FROM media_items WHERE slug = ?",
                (item["slug"],),
            ).fetchone()
            created_at = datetime_now_iso()
            updated_at = datetime_now_iso()
            common_payload = (
                "audio",
                item["title"],
                item["summary"],
                item["speaker"],
                item["series_name"],
                index,
                item["publish_date"],
                item["duration_seconds"],
                "paid",
                "published",
                media_url,
                media_url,
                media_url,
                item["body_markdown"],
                item["transcript_markdown"],
                "",
                index,
                updated_at,
            )
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO media_items (
                        slug,
                        kind,
                        title,
                        summary,
                        speaker,
                        series_name,
                        episode_number,
                        publish_date,
                        duration_seconds,
                        visibility,
                        status,
                        media_url,
                        preview_url,
                        source_url,
                        body_markdown,
                        transcript_markdown,
                        script_markdown,
                        chapter_payload_json,
                        sort_order,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)
                    """,
                    (
                        item["slug"],
                        *common_payload[:-1],
                        created_at,
                        common_payload[-1],
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE media_items
                    SET kind = ?,
                        title = ?,
                        summary = ?,
                        speaker = ?,
                        series_name = ?,
                        episode_number = ?,
                        publish_date = ?,
                        duration_seconds = ?,
                        visibility = ?,
                        status = ?,
                        media_url = ?,
                        preview_url = ?,
                        source_url = ?,
                        body_markdown = ?,
                        transcript_markdown = ?,
                        script_markdown = ?,
                        sort_order = ?,
                        updated_at = ?
                    WHERE slug = ?
                    """,
                    (*common_payload, item["slug"]),
                )
        connection.execute(
            """
            UPDATE media_items
            SET visibility = 'paid'
            WHERE kind = 'audio' AND visibility <> 'paid'
            """
        )
        connection.commit()
