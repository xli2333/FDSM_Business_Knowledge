from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from backend.database import connection_scope

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


def _load_json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _serialize_article_candidate(row) -> dict:
    return {
        "entity_type": "article",
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "subtitle": row["publish_date"],
        "description": row["excerpt"] or "",
    }


def _serialize_topic_candidate(row) -> dict:
    return {
        "entity_type": "topic",
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "subtitle": row["type"],
        "description": row["description"] or "",
    }


def _serialize_tag_candidate(row) -> dict:
    return {
        "entity_type": "tag",
        "id": row["id"],
        "slug": row["slug"],
        "title": row["name"],
        "subtitle": row["category"],
        "description": f'{row["article_count"] or 0} articles',
    }


def _serialize_column_candidate(row) -> dict:
    return {
        "entity_type": "column",
        "id": row["id"],
        "slug": row["slug"],
        "title": row["name"],
        "subtitle": row["icon"] or "",
        "description": row["description"] or "",
    }


def _resolve_slot_item(connection, entity_type: str, entity_id: int | None, entity_slug: str | None) -> dict | None:
    if entity_type == "article":
        if not entity_id:
            return None
        row = connection.execute(
            """
            SELECT id, slug, title, publish_date, excerpt
            FROM articles
            WHERE id = ?
            """,
            (entity_id,),
        ).fetchone()
        return _serialize_article_candidate(row) if row else None

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
        return _serialize_topic_candidate(row) if row else None

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
        return _serialize_tag_candidate(row) if row else None

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
        return _serialize_column_candidate(row) if row else None

    return None


def _validate_candidate_payload(connection, slot_key: str, payload: dict) -> tuple[str, int | None, str | None, dict]:
    entity_type = _normalize_entity_type(slot_key, payload.get("entity_type"))
    entity_id = payload.get("id")
    entity_slug = str(payload.get("slug") or "").strip() or None
    try:
        entity_id = int(entity_id) if entity_id is not None else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid candidate id") from exc
    serialized = _resolve_slot_item(connection, entity_type, entity_id, entity_slug)
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


def search_content_operation_candidates(entity_type: str, query: str = "", limit: int = 12) -> list[dict]:
    safe_limit = _normalize_limit(limit)
    normalized_type = str(entity_type or "").strip()
    text = str(query or "").strip()
    like_value = f"%{text}%"
    with connection_scope() as connection:
        if normalized_type == "article":
            if text:
                rows = connection.execute(
                    """
                    SELECT id, slug, title, publish_date, excerpt
                    FROM articles
                    WHERE title LIKE ? OR slug LIKE ?
                    ORDER BY publish_date DESC, id DESC
                    LIMIT ?
                    """,
                    (like_value, like_value, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, slug, title, publish_date, excerpt
                    FROM articles
                    ORDER BY publish_date DESC, id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return [_serialize_article_candidate(row) for row in rows]

        if normalized_type == "topic":
            if text:
                rows = connection.execute(
                    """
                    SELECT id, slug, title, description, type
                    FROM topics
                    WHERE status = 'published' AND (title LIKE ? OR slug LIKE ?)
                    ORDER BY updated_at DESC, title ASC
                    LIMIT ?
                    """,
                    (like_value, like_value, safe_limit),
                ).fetchall()
            else:
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
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return [_serialize_topic_candidate(row) for row in rows]

        if normalized_type == "tag":
            if text:
                rows = connection.execute(
                    """
                    SELECT id, slug, name, category, article_count
                    FROM tags
                    WHERE name LIKE ? OR slug LIKE ?
                    ORDER BY article_count DESC, name ASC
                    LIMIT ?
                    """,
                    (like_value, like_value, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, slug, name, category, article_count
                    FROM tags
                    ORDER BY article_count DESC, name ASC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return [_serialize_tag_candidate(row) for row in rows]

        if normalized_type == "column":
            if text:
                rows = connection.execute(
                    """
                    SELECT id, slug, name, description, icon
                    FROM columns
                    WHERE name LIKE ? OR slug LIKE ?
                    ORDER BY sort_order ASC, name ASC
                    LIMIT ?
                    """,
                    (like_value, like_value, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, slug, name, description, icon
                    FROM columns
                    ORDER BY sort_order ASC, name ASC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return [_serialize_column_candidate(row) for row in rows]

    raise HTTPException(status_code=400, detail="Unsupported candidate type")


def list_home_content_slots() -> dict[str, list[dict]]:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT slot_key, entity_type, entity_id, entity_slug, sort_order, metadata_json
            FROM home_content_slots
            WHERE is_active = 1
            ORDER BY slot_key ASC, sort_order ASC, id ASC
            """
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


def get_content_operations_state() -> dict:
    with connection_scope() as connection:
        slot_rows = connection.execute(
            """
            SELECT id, slot_key, entity_type, entity_id, entity_slug, sort_order
            FROM home_content_slots
            WHERE is_active = 1
            ORDER BY slot_key ASC, sort_order ASC, id ASC
            """
        ).fetchall()
        grouped: dict[str, list[dict]] = {slot_key: [] for slot_key in HOME_SLOT_DEFINITIONS}
        for row in slot_rows:
            item = _resolve_slot_item(connection, row["entity_type"], row["entity_id"], row["entity_slug"])
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
        "sections": sections,
        "trending": {
            **get_trending_config(),
            "windows": list(TRENDING_WINDOWS.keys()),
        },
    }


def update_content_operations_section(slot_key: str, items: list[dict]) -> dict:
    normalized_slot_key = _normalize_slot_key(slot_key)
    definition = HOME_SLOT_DEFINITIONS[normalized_slot_key]
    max_items = int(definition["max_items"])
    if len(items) > max_items:
        raise HTTPException(status_code=400, detail=f"{normalized_slot_key} supports at most {max_items} items")

    updated_at = _now_iso()
    with connection_scope() as connection:
        normalized_items: list[tuple[str, int | None, str | None, int, str, str]] = []
        seen_keys: set[tuple[str, int | None, str | None]] = set()
        for index, item in enumerate(items):
            entity_type, entity_id, entity_slug, _serialized = _validate_candidate_payload(connection, normalized_slot_key, item)
            dedupe_key = (entity_type, entity_id, entity_slug)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            normalized_items.append((entity_type, entity_id, entity_slug, index, updated_at, updated_at))

        connection.execute("DELETE FROM home_content_slots WHERE slot_key = ?", (normalized_slot_key,))
        if normalized_items:
            connection.executemany(
                """
                INSERT INTO home_content_slots (
                    slot_key,
                    entity_type,
                    entity_id,
                    entity_slug,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(normalized_slot_key, *item) for item in normalized_items],
            )
        connection.commit()

    return get_content_operations_state()


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
