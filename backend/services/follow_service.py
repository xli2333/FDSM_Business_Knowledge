from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException

from backend.database import connection_scope
from backend.services.catalog_service import _serialize_articles
from backend.services.membership_service import get_membership_profile

VALID_FOLLOW_TYPES = {"tag", "column", "topic"}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _require_user(user: dict | None) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def _normalize_follow_type(value: str | None) -> str:
    normalized = (value or "").strip()
    if normalized not in VALID_FOLLOW_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported follow type")
    return normalized


def _resolve_entity(connection, entity_type: str, entity_slug: str) -> tuple[str, str]:
    slug = (entity_slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="Entity slug is required")
    if entity_type == "tag":
        row = connection.execute(
            "SELECT slug, name FROM tags WHERE slug = ? OR name = ? LIMIT 1",
            (slug, slug),
        ).fetchone()
    elif entity_type == "column":
        row = connection.execute(
            "SELECT slug, name FROM columns WHERE slug = ? LIMIT 1",
            (slug,),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT slug, title AS name FROM topics WHERE slug = ? AND status = 'published' LIMIT 1",
            (slug,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Follow target not found")
    return row["slug"], row["name"]


def list_follows(user: dict | None) -> dict:
    current_user = _require_user(user)
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT entity_type, entity_slug, entity_label, created_at
            FROM user_follows
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (current_user["id"],),
        ).fetchall()
    items = [dict(row) for row in rows]
    return {"items": items, "total": len(items)}


def toggle_follow(user: dict | None, *, entity_type: str, entity_slug: str, active: bool = True) -> dict:
    current_user = _require_user(user)
    normalized_type = _normalize_follow_type(entity_type)

    with connection_scope() as connection:
        normalized_slug, entity_label = _resolve_entity(connection, normalized_type, entity_slug)
        if active:
            created_at = _now_iso()
            connection.execute(
                """
                INSERT OR IGNORE INTO user_follows (user_id, entity_type, entity_slug, entity_label, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (current_user["id"], normalized_type, normalized_slug, entity_label, created_at),
            )
            row = connection.execute(
                """
                SELECT entity_type, entity_slug, entity_label, created_at
                FROM user_follows
                WHERE user_id = ? AND entity_type = ? AND entity_slug = ?
                """,
                (current_user["id"], normalized_type, normalized_slug),
            ).fetchone()
            connection.commit()
            return {"active": True, "item": dict(row) if row else None}

        connection.execute(
            """
            DELETE FROM user_follows
            WHERE user_id = ? AND entity_type = ? AND entity_slug = ?
            """,
            (current_user["id"], normalized_type, normalized_slug),
        )
        connection.commit()
    return {"active": False, "item": None}


def get_watchlist(
    user: dict | None,
    limit: int = 24,
    entity_type: str | None = None,
    entity_slug: str | None = None,
) -> dict:
    current_user = _require_user(user)
    safe_limit = max(1, min(limit, 48))
    membership = get_membership_profile(current_user)

    with connection_scope() as connection:
        follow_params: tuple = (current_user["id"],)
        follow_where = "WHERE user_id = ?"
        is_filtered = bool(entity_type or entity_slug)

        if is_filtered:
            if not entity_type or not entity_slug:
                raise HTTPException(status_code=400, detail="Watchlist filter requires entity_type and entity_slug")
            normalized_type = _normalize_follow_type(entity_type)
            normalized_slug, _ = _resolve_entity(connection, normalized_type, entity_slug)
            follow_where += " AND entity_type = ? AND entity_slug = ?"
            follow_params = (current_user["id"], normalized_type, normalized_slug)

        follow_rows = connection.execute(
            f"""
            SELECT entity_type, entity_slug, entity_label, created_at
            FROM user_follows
            {follow_where}
            ORDER BY created_at DESC, id DESC
            """,
            follow_params,
        ).fetchall()

        matches: dict[int, set[str]] = defaultdict(set)
        per_follow_limit = safe_limit if is_filtered else 10
        for follow in follow_rows:
            entity_type = follow["entity_type"]
            entity_slug = follow["entity_slug"]
            entity_label = follow["entity_label"]
            if entity_type == "tag":
                article_rows = connection.execute(
                    """
                    SELECT a.id
                    FROM article_tags at
                    JOIN tags t ON t.id = at.tag_id
                    JOIN articles a ON a.id = at.article_id
                    WHERE t.slug = ?
                    ORDER BY a.publish_date DESC, a.id DESC
                    LIMIT ?
                    """,
                    (entity_slug, per_follow_limit),
                ).fetchall()
            elif entity_type == "column":
                article_rows = connection.execute(
                    """
                    SELECT a.id
                    FROM article_columns ac
                    JOIN columns c ON c.id = ac.column_id
                    JOIN articles a ON a.id = ac.article_id
                    WHERE c.slug = ?
                    ORDER BY a.publish_date DESC, a.id DESC
                    LIMIT ?
                    """,
                    (entity_slug, per_follow_limit),
                ).fetchall()
            else:
                article_rows = connection.execute(
                    """
                    SELECT a.id
                    FROM topic_articles ta
                    JOIN topics t ON t.id = ta.topic_id
                    JOIN articles a ON a.id = ta.article_id
                    WHERE t.slug = ?
                    ORDER BY a.publish_date DESC, a.id DESC
                    LIMIT ?
                    """,
                    (entity_slug, per_follow_limit),
                ).fetchall()

            for row in article_rows:
                matches[row["id"]].add(entity_label)

        article_ids = list(matches.keys())
        if not article_ids:
            return {
                "follows": [dict(row) for row in follow_rows],
                "items": [],
                "total": 0,
            }

        placeholders = ",".join("?" for _ in article_ids)
        rows = connection.execute(
            f"""
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type,
                main_topic, view_count, cover_image_path, link
            FROM articles
            WHERE id IN ({placeholders})
            """,
            article_ids,
        ).fetchall()
        serialized = _serialize_articles(
            connection,
            rows,
            current_user_id=current_user["id"],
            membership_profile=membership,
        )

    serialized.sort(key=lambda item: (item["publish_date"], item["view_count"], item["id"]), reverse=True)
    items = [
        {
            **item,
            "matched_entities": sorted(matches.get(item["id"], set())),
        }
        for item in serialized[:safe_limit]
    ]
    return {
        "follows": [dict(row) for row in follow_rows],
        "items": items,
        "total": len(items),
    }
