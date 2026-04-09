from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException

from backend.config import MEDIA_UPLOADS_DIR
from backend.database import connection_scope
from backend.services.local_media_library import LOCAL_AUDIO_ITEMS

VISIBILITY_LABELS = {
    "public": "公开",
    "member": "会员",
    "paid": "付费",
}
VALID_VISIBILITY = set(VISIBILITY_LABELS)
VALID_KINDS = {"audio", "video"}
VALID_STATUSES = {"draft", "published"}
VALID_UPLOAD_USAGES = {"media", "preview"}
ALLOWED_UPLOAD_EXTENSIONS = {
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg"},
    "video": {".mp4", ".mov", ".m4v", ".webm"},
}
LEGACY_AUDIO_SEED_SLUGS = {
    "audio-ai-decision-lab",
    "audio-case-briefing-weekly",
    "audio-chairman-private-brief",
}


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


def _extract_excerpt(value: str | None, limit: int = 160) -> str:
    compact = _compact_text(value)
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


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


def _sanitize_filename(value: str) -> str:
    raw = Path(value or "media.bin").name
    stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", Path(raw).stem).strip("-")
    suffix = Path(raw).suffix.lower()
    return f"{stem[:80] or 'media'}{suffix}"


def _resolve_access(visibility: str, membership: dict | None) -> tuple[bool, str | None]:
    if membership is None:
        return True, None
    if visibility == "public":
        return True, None
    if visibility == "member":
        if membership["can_access_member"]:
            return True, None
        return False, "登录成为免费会员后可解锁完整音视频内容。"
    if visibility == "paid":
        if membership["can_access_paid"]:
            return True, None
        if membership["can_access_member"]:
            return False, "升级为付费会员后可观看或收听完整内容。"
        return False, "登录并升级为付费会员后可解锁完整内容。"
    return False, "内容权限配置异常。"


def _serialize_media_row(row, membership: dict | None = None) -> dict:
    chapters = _load_chapters(row["chapter_payload_json"])
    accessible, gate_copy = _resolve_access(row["visibility"], membership)
    transcript_excerpt = _extract_excerpt(row["transcript_markdown"] or row["body_markdown"] or row["summary"])
    return {
        "id": row["id"],
        "slug": row["slug"],
        "kind": row["kind"],
        "title": row["title"],
        "summary": row["summary"],
        "speaker": row["speaker"],
        "series_name": row["series_name"],
        "episode_number": row["episode_number"],
        "publish_date": row["publish_date"],
        "duration_seconds": row["duration_seconds"],
        "visibility": row["visibility"],
        "visibility_label": VISIBILITY_LABELS.get(row["visibility"], row["visibility"]),
        "status": row["status"],
        "accessible": accessible,
        "gate_copy": gate_copy,
        "cover_image_url": row["cover_image_url"],
        "media_url": row["media_url"],
        "preview_url": row["preview_url"],
        "source_url": row["source_url"],
        "transcript_excerpt": transcript_excerpt,
        "chapter_count": len(chapters),
        "transcript_markdown": row["transcript_markdown"] or "",
        "body_markdown": row["body_markdown"] or "",
        "chapters": chapters,
    }


def _unique_slug(connection, base_slug: str, *, exclude_id: int | None = None) -> str:
    candidate = base_slug or f"media-{date.today().isoformat()}"
    suffix = 1
    while True:
        row = connection.execute("SELECT id FROM media_items WHERE slug = ?", (candidate,)).fetchone()
        if row is None or (exclude_id is not None and row["id"] == exclude_id):
            return candidate
        candidate = f"{base_slug[:72]}-{suffix}"
        suffix += 1


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
                chapter_payload_json
            FROM media_items
            WHERE kind = ? AND status = 'published'
            ORDER BY COALESCE(series_name, title) ASC, episode_number DESC, publish_date DESC, sort_order ASC, id DESC
            LIMIT ?
            """,
            (normalized_kind, safe_limit),
        ).fetchall()
        count_rows = connection.execute(
            """
            SELECT visibility, COUNT(*) AS total
            FROM media_items
            WHERE kind = ? AND status = 'published'
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


def list_admin_media_items(kind: str | None = None, status: str | None = None, limit: int = 60) -> dict:
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
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    with connection_scope() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM media_items
            {where_sql}
            ORDER BY kind ASC, COALESCE(series_name, title) ASC, episode_number DESC, publish_date DESC, id DESC
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
        row = connection.execute("SELECT * FROM media_items WHERE id = ?", (media_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    return _serialize_media_row(row, membership=None)


def create_media_item(payload: dict) -> dict:
    sync_local_audio_library()
    kind = _normalize_kind(payload.get("kind"))
    title = _compact_text(payload.get("title"))
    summary = _compact_text(payload.get("summary"))
    if not title:
        raise HTTPException(status_code=400, detail="Media title is required")
    if not summary:
        raise HTTPException(status_code=400, detail="Media summary is required")

    timestamp = datetime_now_iso()
    with connection_scope() as connection:
        desired_slug = _slugify(payload.get("slug") or title)
        slug = _unique_slug(connection, desired_slug)
        chapters = payload.get("chapters") or []
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
                chapter_payload_json,
                sort_order,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                slug,
                kind,
                title,
                summary,
                _compact_text(payload.get("speaker")),
                _compact_text(payload.get("series_name")),
                _normalize_episode_number(payload.get("episode_number")),
                _normalize_publish_date(payload.get("publish_date")),
                max(0, int(payload.get("duration_seconds") or 0)),
                _normalize_visibility(payload.get("visibility")),
                _normalize_status(payload.get("status")),
                _compact_text(payload.get("cover_image_url")),
                _compact_text(payload.get("media_url")),
                _compact_text(payload.get("preview_url")),
                _compact_text(payload.get("source_url")),
                payload.get("body_markdown") or "",
                payload.get("transcript_markdown") or "",
                json.dumps(chapters, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        media_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.commit()
    return get_admin_media_item(media_id)


def update_media_item(media_id: int, payload: dict) -> dict:
    sync_local_audio_library()
    with connection_scope() as connection:
        row = connection.execute("SELECT * FROM media_items WHERE id = ?", (media_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Media item not found")
        current = dict(row)

        if "kind" in payload and payload.get("kind") is not None:
            current["kind"] = _normalize_kind(payload.get("kind"))
        if "title" in payload and payload.get("title") is not None:
            current["title"] = _compact_text(payload.get("title"))
        if "summary" in payload and payload.get("summary") is not None:
            current["summary"] = _compact_text(payload.get("summary"))
        if not current["title"]:
            raise HTTPException(status_code=400, detail="Media title is required")
        if not current["summary"]:
            raise HTTPException(status_code=400, detail="Media summary is required")

        if "slug" in payload and payload.get("slug") is not None:
            current["slug"] = _unique_slug(connection, _slugify(payload.get("slug") or current["title"]), exclude_id=media_id)
        if "speaker" in payload:
            current["speaker"] = _compact_text(payload.get("speaker"))
        if "series_name" in payload:
            current["series_name"] = _compact_text(payload.get("series_name"))
        if "episode_number" in payload and payload.get("episode_number") is not None:
            current["episode_number"] = _normalize_episode_number(payload.get("episode_number"))
        if "publish_date" in payload and payload.get("publish_date") is not None:
            current["publish_date"] = _normalize_publish_date(payload.get("publish_date"))
        if "duration_seconds" in payload and payload.get("duration_seconds") is not None:
            current["duration_seconds"] = max(0, int(payload.get("duration_seconds") or 0))
        if "visibility" in payload and payload.get("visibility") is not None:
            current["visibility"] = _normalize_visibility(payload.get("visibility"))
        if "status" in payload and payload.get("status") is not None:
            current["status"] = _normalize_status(payload.get("status"))
        if "cover_image_url" in payload:
            current["cover_image_url"] = _compact_text(payload.get("cover_image_url"))
        if "media_url" in payload:
            current["media_url"] = _compact_text(payload.get("media_url"))
        if "preview_url" in payload:
            current["preview_url"] = _compact_text(payload.get("preview_url"))
        if "source_url" in payload:
            current["source_url"] = _compact_text(payload.get("source_url"))
        if "body_markdown" in payload:
            current["body_markdown"] = payload.get("body_markdown") or ""
        if "transcript_markdown" in payload:
            current["transcript_markdown"] = payload.get("transcript_markdown") or ""
        if "chapters" in payload:
            current["chapter_payload_json"] = json.dumps(payload.get("chapters") or [], ensure_ascii=False)

        current["updated_at"] = datetime_now_iso()
        connection.execute(
            """
            UPDATE media_items
            SET
                slug = ?,
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
                preview_url = ?,
                source_url = ?,
                body_markdown = ?,
                transcript_markdown = ?,
                chapter_payload_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                current["slug"],
                current["kind"],
                current["title"],
                current["summary"],
                current["speaker"],
                current["series_name"],
                current["episode_number"],
                current["publish_date"],
                current["duration_seconds"],
                current["visibility"],
                current["status"],
                current["cover_image_url"],
                current["media_url"],
                current["preview_url"],
                current["source_url"],
                current["body_markdown"],
                current["transcript_markdown"],
                current["chapter_payload_json"],
                current["updated_at"],
                media_id,
            ),
        )
        connection.commit()
    return get_admin_media_item(media_id)


def datetime_now_iso() -> str:
    from datetime import datetime

    return datetime.now().replace(microsecond=0).isoformat()


def upload_media_asset(kind: str, usage: str, filename: str, raw_bytes: bytes, content_type: str | None = None) -> dict:
    normalized_kind = _normalize_kind(kind)
    normalized_usage = (usage or "").strip() or "media"
    if normalized_usage not in VALID_UPLOAD_USAGES:
        raise HTTPException(status_code=400, detail="Unsupported media upload usage")

    safe_name = _sanitize_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS[normalized_kind]:
        raise HTTPException(status_code=400, detail="Unsupported media file type")

    target_dir = MEDIA_UPLOADS_DIR / normalized_kind / normalized_usage
    target_dir.mkdir(parents=True, exist_ok=True)
    base_stem = Path(safe_name).stem[:80] or normalized_kind
    timestamp = datetime_now_iso().replace(":", "-")
    final_name = f"{timestamp}-{base_stem}{suffix}"
    target_path = target_dir / final_name
    target_path.write_bytes(raw_bytes)

    relative_url = f"/media-uploads/{normalized_kind}/{normalized_usage}/{quote(final_name)}"
    return {
        "kind": normalized_kind,
        "usage": normalized_usage,
        "filename": final_name,
        "content_type": content_type,
        "size_bytes": len(raw_bytes),
        "url": relative_url,
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
            payload = (
                "audio",
                item["title"],
                item["summary"],
                item["speaker"],
                item["series_name"],
                index,
                item["publish_date"],
                item["duration_seconds"],
                "public",
                "published",
                media_url,
                media_url,
                media_url,
                item["body_markdown"],
                item["transcript_markdown"],
                index,
                datetime_now_iso(),
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
                        chapter_payload_json,
                        sort_order,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)
                    """,
                    (
                        item["slug"],
                        *payload,
                        datetime_now_iso(),
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
                        sort_order = ?,
                        updated_at = ?
                    WHERE slug = ?
                    """,
                    (*payload, item["slug"]),
                )
        connection.commit()
