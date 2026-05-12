from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from backend.database import connection_scope
from backend.services.article_ai_output_service import build_current_article_source_hash
from backend.services.content_localization import (
    english_article_ready,
    localize_column_payload,
    localize_tag_payload,
    localize_topic_payload,
)

HOME_SLOT_DEFINITIONS: dict[str, dict[str, object]] = {
    "hero": {"entity_type": "article", "max_items": 1},
    "editors_picks": {"entity_type": "article", "max_items": 6},
    "quick_tags": {"entity_type": "tag", "max_items": 6},
    "topic_starters": {"entity_type": "topic", "max_items": 2},
    "column_navigation": {"entity_type": "column", "max_items": 6},
    "topic_square": {"entity_type": "topic", "max_items": 6},
}
TRENDING_WINDOWS = {"day": 1, "week": 7, "month": 30}
DEFAULT_TRENDING_CONFIG = {
    "default_window": "week",
    "view_weight": 1.0,
    "like_weight": 4.0,
    "bookmark_weight": 6.0,
}
SUPPORTED_CONTENT_LANGUAGES = ("zh", "en")


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _normalize_slot_key(value: str | None) -> str:
    slot_key = str(value or "").strip()
    if slot_key not in HOME_SLOT_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Unsupported home content slot")
    return slot_key


def _normalize_entity_type(slot_key: str, value: str | None) -> str:
    entity_type = str(value or "").strip()
    expected = str(HOME_SLOT_DEFINITIONS[slot_key]["entity_type"])
    if entity_type != expected:
        raise HTTPException(status_code=400, detail=f"{slot_key} only accepts {expected}")
    return entity_type


def _normalize_trending_window(value: str | None) -> str:
    window = str(value or "").strip() or DEFAULT_TRENDING_CONFIG["default_window"]
    if window not in TRENDING_WINDOWS:
        raise HTTPException(status_code=400, detail="Unsupported trending window")
    return window


def _normalize_limit(limit: int, max_limit: int = 24) -> int:
    return max(1, min(int(limit or 12), max_limit))


def _normalize_content_language(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return "en" if normalized == "en" else "zh"


def _load_json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _matches_candidate_query(candidate: dict, query: str) -> bool:
    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return True
    haystack = " ".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("slug") or ""),
            str(candidate.get("subtitle") or ""),
            str(candidate.get("description") or ""),
        ]
    ).lower()
    return normalized_query in haystack


def _fetch_article_translation_map(connection, article_rows: list) -> dict[int, dict[str, str]]:
    article_ids = [int(row["id"]) for row in article_rows if row["id"] is not None]
    if not article_ids:
        return {}

    current_hashes = {int(row["id"]): build_current_article_source_hash(row) for row in article_rows}
    placeholders = ",".join("?" for _ in article_ids)
    translation_rows = connection.execute(
        f"""
        SELECT article_id, source_hash, title, excerpt, updated_at, created_at
        FROM article_translations
        WHERE article_id IN ({placeholders}) AND target_lang = 'en'
        ORDER BY article_id ASC, updated_at DESC, created_at DESC
        """,
        article_ids,
    ).fetchall()

    translation_map: dict[int, dict[str, str]] = {}
    for row in translation_rows:
        article_id = int(row["article_id"])
        if article_id in translation_map:
            continue
        if str(row["source_hash"] or "") != str(current_hashes.get(article_id) or ""):
            continue
        translation_map[article_id] = {
            "title": str(row["title"] or "").strip(),
            "excerpt": str(row["excerpt"] or "").strip(),
        }

    missing_ids = [article_id for article_id in article_ids if article_id not in translation_map]
    if not missing_ids:
        return translation_map

    fallback_placeholders = ",".join("?" for _ in missing_ids)
    ai_rows = connection.execute(
        f"""
        SELECT article_id, source_hash, translation_title_en, translation_excerpt_en, updated_at
        FROM article_ai_outputs
        WHERE article_id IN ({fallback_placeholders})
          AND translation_status = 'completed'
          AND COALESCE(translation_content_en, '') != ''
        ORDER BY article_id ASC, updated_at DESC
        """,
        missing_ids,
    ).fetchall()
    for row in ai_rows:
        article_id = int(row["article_id"])
        if article_id in translation_map:
            continue
        if str(row["source_hash"] or "") != str(current_hashes.get(article_id) or ""):
            continue
        translation_map[article_id] = {
            "title": str(row["translation_title_en"] or "").strip(),
            "excerpt": str(row["translation_excerpt_en"] or "").strip(),
        }
    return translation_map


def _serialize_article_candidate(row, *, language: str, translation_map: dict[int, dict[str, str]] | None = None) -> dict | None:
    translation = (translation_map or {}).get(int(row["id"]))
    title = str(row["title"] or "").strip()
    description = str(row["excerpt"] or "").strip()
    if language == "en":
        if not translation:
            return None
        title = str(translation.get("title") or "").strip() or title
        description = str(translation.get("excerpt") or "").strip() or description
    payload = {
        "entity_type": "article",
        "id": row["id"],
        "slug": row["slug"],
        "title": title,
        "subtitle": row["publish_date"],
        "description": description,
    }
    if language == "en" and not english_article_ready(payload):
        return None
    return payload


def _serialize_topic_candidate(row, *, language: str) -> dict:
    payload = localize_topic_payload(dict(row), language=language)
    return {
        "entity_type": "topic",
        "id": payload["id"],
        "slug": payload["slug"],
        "title": payload["title"],
        "subtitle": payload["type"],
        "description": payload.get("description") or "",
    }


def _serialize_tag_candidate(row, *, language: str) -> dict | None:
    payload = localize_tag_payload(dict(row), language=language)
    if payload is None:
        return None
    return {
        "entity_type": "tag",
        "id": payload["id"],
        "slug": payload["slug"],
        "title": payload["name"],
        "subtitle": payload["category"],
        "description": (f'{payload["article_count"] or 0} articles' if language == "en" else f'{payload["article_count"] or 0} 篇文章'),
    }


def _serialize_column_candidate(row, *, language: str) -> dict:
    payload = localize_column_payload(dict(row), language=language)
    return {
        "entity_type": "column",
        "id": payload["id"],
        "slug": payload["slug"],
        "title": payload["name"],
        "subtitle": payload.get("icon") or "",
        "description": payload.get("description") or "",
    }


def _resolve_slot_item(connection, entity_type: str, entity_id: int | None, entity_slug: str | None, *, language: str) -> dict | None:
    if entity_type == "article":
        if not entity_id:
            return None
        row = connection.execute(
            """
            SELECT id, slug, title, publish_date, excerpt, main_topic, content, COALESCE(access_level, 'public') AS access_level
            FROM articles
            WHERE id = ?
            """,
            (entity_id,),
        ).fetchone()
        if not row:
            return None
        translation_map = _fetch_article_translation_map(connection, [row]) if language == "en" else {}
        return _serialize_article_candidate(row, language=language, translation_map=translation_map)

    if entity_type == "topic":
        if entity_slug:
            row = connection.execute(
                """
                SELECT id, slug, title, description, type
                FROM topics
                WHERE slug = ? AND status = 'published'
                """,
                (entity_slug,),
            ).fetchone()
        elif entity_id:
            row = connection.execute(
                """
                SELECT id, slug, title, description, type
                FROM topics
                WHERE id = ? AND status = 'published'
                """,
                (entity_id,),
            ).fetchone()
        else:
            row = None
        return _serialize_topic_candidate(row, language=language) if row else None

    if entity_type == "tag":
        if entity_slug:
            row = connection.execute(
                """
                SELECT id, slug, name, category, article_count
                FROM tags
                WHERE slug = ?
                """,
                (entity_slug,),
            ).fetchone()
        elif entity_id:
            row = connection.execute(
                """
                SELECT id, slug, name, category, article_count
                FROM tags
                WHERE id = ?
                """,
                (entity_id,),
            ).fetchone()
        else:
            row = None
        return _serialize_tag_candidate(row, language=language) if row else None

    if entity_type == "column":
        if entity_slug:
            row = connection.execute(
                """
                SELECT id, slug, name, description, icon
                FROM columns
                WHERE slug = ?
                """,
                (entity_slug,),
            ).fetchone()
        elif entity_id:
            row = connection.execute(
                """
                SELECT id, slug, name, description, icon
                FROM columns
                WHERE id = ?
                """,
                (entity_id,),
            ).fetchone()
        else:
            row = None
        return _serialize_column_candidate(row, language=language) if row else None

    return None


def _validate_candidate_payload(connection, slot_key: str, payload: dict, *, language: str) -> tuple[str, int | None, str | None, dict]:
    entity_type = _normalize_entity_type(slot_key, payload.get("entity_type"))
    entity_id = payload.get("id")
    entity_slug = str(payload.get("slug") or "").strip() or None
    try:
        entity_id = int(entity_id) if entity_id is not None else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid candidate id") from exc
    serialized = _resolve_slot_item(connection, entity_type, entity_id, entity_slug, language=language)
    if serialized is None:
        raise HTTPException(status_code=404, detail="Selected content item no longer exists")
    return entity_type, entity_id, entity_slug or serialized.get("slug"), serialized


def _get_trending_config_row(connection):
    return connection.execute(
        """
        SELECT default_window, view_weight, like_weight, bookmark_weight, updated_at
        FROM home_trending_config
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()


def get_trending_config() -> dict:
    with connection_scope() as connection:
        row = _get_trending_config_row(connection)
        if row is None:
            return {**DEFAULT_TRENDING_CONFIG, "updated_at": None}
        return {
            "default_window": _normalize_trending_window(row["default_window"]),
            "view_weight": float(row["view_weight"] or DEFAULT_TRENDING_CONFIG["view_weight"]),
            "like_weight": float(row["like_weight"] or DEFAULT_TRENDING_CONFIG["like_weight"]),
            "bookmark_weight": float(row["bookmark_weight"] or DEFAULT_TRENDING_CONFIG["bookmark_weight"]),
            "updated_at": row["updated_at"],
        }


def update_trending_config(payload: dict) -> dict:
    default_window = _normalize_trending_window(payload.get("default_window"))
    try:
        view_weight = float(payload.get("view_weight", DEFAULT_TRENDING_CONFIG["view_weight"]))
        like_weight = float(payload.get("like_weight", DEFAULT_TRENDING_CONFIG["like_weight"]))
        bookmark_weight = float(payload.get("bookmark_weight", DEFAULT_TRENDING_CONFIG["bookmark_weight"]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Trending weights must be numeric") from exc

    if min(view_weight, like_weight, bookmark_weight) < 0:
        raise HTTPException(status_code=400, detail="Trending weights cannot be negative")

    updated_at = _now_iso()
    with connection_scope() as connection:
        existing = connection.execute("SELECT id FROM home_trending_config ORDER BY id ASC LIMIT 1").fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO home_trending_config (
                    default_window,
                    view_weight,
                    like_weight,
                    bookmark_weight,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (default_window, view_weight, like_weight, bookmark_weight, updated_at),
            )
        else:
            connection.execute(
                """
                UPDATE home_trending_config
                SET default_window = ?,
                    view_weight = ?,
                    like_weight = ?,
                    bookmark_weight = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (default_window, view_weight, like_weight, bookmark_weight, updated_at, existing["id"]),
            )
        connection.commit()
    return get_trending_config()


def search_content_operation_candidates(entity_type: str, query: str = "", limit: int = 12, *, language: str = "zh") -> list[dict]:
    safe_limit = _normalize_limit(limit)
    normalized_type = str(entity_type or "").strip()
    normalized_language = _normalize_content_language(language)
    text = str(query or "").strip()
    with connection_scope() as connection:
        if normalized_type == "article":
            rows = connection.execute(
                """
                SELECT id, slug, title, publish_date, excerpt, main_topic, content, COALESCE(access_level, 'public') AS access_level
                FROM articles
                ORDER BY publish_date DESC, id DESC
                """
            ).fetchall()
            translation_map = _fetch_article_translation_map(connection, rows) if normalized_language == "en" else {}
            payload: list[dict] = []
            for row in rows:
                candidate = _serialize_article_candidate(row, language=normalized_language, translation_map=translation_map)
                if not candidate or not _matches_candidate_query(candidate, text):
                    continue
                payload.append(candidate)
                if len(payload) >= safe_limit:
                    break
            return payload

        if normalized_type == "topic":
            rows = connection.execute(
                """
                SELECT id, slug, title, description, type
                FROM topics
                WHERE status = 'published'
                ORDER BY
                    CASE type
                        WHEN 'seed' THEN 1
                        WHEN 'auto' THEN 2
                        WHEN 'editorial' THEN 3
                        WHEN 'timeline' THEN 4
                        ELSE 5
                    END,
                    view_count DESC,
                    title ASC
                """
            ).fetchall()
            payload = []
            for row in rows:
                candidate = _serialize_topic_candidate(row, language=normalized_language)
                if not _matches_candidate_query(candidate, text):
                    continue
                payload.append(candidate)
                if len(payload) >= safe_limit:
                    break
            return payload

        if normalized_type == "tag":
            rows = connection.execute(
                """
                SELECT id, slug, name, category, article_count
                FROM tags
                ORDER BY article_count DESC, name ASC
                """
            ).fetchall()
            payload = []
            for row in rows:
                candidate = _serialize_tag_candidate(row, language=normalized_language)
                if not candidate or not _matches_candidate_query(candidate, text):
                    continue
                payload.append(candidate)
                if len(payload) >= safe_limit:
                    break
            return payload

        if normalized_type == "column":
            rows = connection.execute(
                """
                SELECT id, slug, name, description, icon
                FROM columns
                ORDER BY sort_order ASC, name ASC
                """
            ).fetchall()
            payload = []
            for row in rows:
                candidate = _serialize_column_candidate(row, language=normalized_language)
                if not _matches_candidate_query(candidate, text):
                    continue
                payload.append(candidate)
                if len(payload) >= safe_limit:
                    break
            return payload

    raise HTTPException(status_code=400, detail="Unsupported candidate type")


def list_home_content_slots(language: str = "zh") -> dict[str, list[dict]]:
    normalized_language = _normalize_content_language(language)
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT slot_key, entity_type, entity_id, entity_slug, sort_order, metadata_json
            FROM home_content_slots
            WHERE is_active = 1 AND language = ?
            ORDER BY slot_key ASC, sort_order ASC, id ASC
            """,
            (normalized_language,),
        ).fetchall()
        grouped: dict[str, list[dict]] = {slot_key: [] for slot_key in HOME_SLOT_DEFINITIONS}
        for row in rows:
            grouped.setdefault(row["slot_key"], []).append(
                {
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "entity_slug": row["entity_slug"],
                    "sort_order": row["sort_order"],
                    "metadata": _load_json_object(row["metadata_json"]),
                }
            )
        return grouped


def get_content_operations_state(language: str = "zh") -> dict:
    normalized_language = _normalize_content_language(language)
    with connection_scope() as connection:
        slot_rows = connection.execute(
            """
            SELECT id, slot_key, entity_type, entity_id, entity_slug, sort_order
            FROM home_content_slots
            WHERE is_active = 1 AND language = ?
            ORDER BY slot_key ASC, sort_order ASC, id ASC
            """,
            (normalized_language,),
        ).fetchall()
        grouped: dict[str, list[dict]] = {slot_key: [] for slot_key in HOME_SLOT_DEFINITIONS}
        for row in slot_rows:
            item = _resolve_slot_item(
                connection,
                row["entity_type"],
                row["entity_id"],
                row["entity_slug"],
                language=normalized_language,
            )
            if item:
                grouped.setdefault(row["slot_key"], []).append(item)

        sections = []
        for slot_key, definition in HOME_SLOT_DEFINITIONS.items():
            sections.append(
                {
                    "slot_key": slot_key,
                    "entity_type": definition["entity_type"],
                    "max_items": int(definition["max_items"]),
                    "items": grouped.get(slot_key, []),
                }
            )

    return {
        "language": normalized_language,
        "available_languages": list(SUPPORTED_CONTENT_LANGUAGES),
        "sections": sections,
        "trending": {
            **get_trending_config(),
            "windows": list(TRENDING_WINDOWS.keys()),
        },
    }


def update_content_operations_section(slot_key: str, items: list[dict], *, language: str = "zh") -> dict:
    normalized_slot_key = _normalize_slot_key(slot_key)
    normalized_language = _normalize_content_language(language)
    definition = HOME_SLOT_DEFINITIONS[normalized_slot_key]
    max_items = int(definition["max_items"])
    if len(items) > max_items:
        raise HTTPException(status_code=400, detail=f"{normalized_slot_key} supports at most {max_items} items")

    updated_at = _now_iso()
    with connection_scope() as connection:
        normalized_items: list[tuple[str, int | None, str | None, int, str, str]] = []
        seen_keys: set[tuple[str, int | None, str | None]] = set()
        for index, item in enumerate(items):
            entity_type, entity_id, entity_slug, _serialized = _validate_candidate_payload(
                connection,
                normalized_slot_key,
                item,
                language=normalized_language,
            )
            dedupe_key = (entity_type, entity_id, entity_slug)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            normalized_items.append((entity_type, entity_id, entity_slug, index, updated_at, updated_at))

        connection.execute(
            "DELETE FROM home_content_slots WHERE language = ? AND slot_key = ?",
            (normalized_language, normalized_slot_key),
        )
        if normalized_items:
            connection.executemany(
                """
                INSERT INTO home_content_slots (
                    language,
                    slot_key,
                    entity_type,
                    entity_id,
                    entity_slug,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(normalized_language, normalized_slot_key, *item) for item in normalized_items],
            )
        connection.commit()

    return get_content_operations_state(language=normalized_language)


def get_trending_sql_parts(window: str) -> dict[str, object]:
    normalized_window = _normalize_trending_window(window)
    days = TRENDING_WINDOWS[normalized_window]
    since_date = (date.today() - timedelta(days=days - 1)).isoformat()
    config = get_trending_config()
    return {
        "window": normalized_window,
        "since_date": since_date,
        "view_weight": float(config["view_weight"]),
        "like_weight": float(config["like_weight"]),
        "bookmark_weight": float(config["bookmark_weight"]),
    }
