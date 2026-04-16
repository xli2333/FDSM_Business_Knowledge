from __future__ import annotations

import re
from datetime import date, datetime

from fastapi import HTTPException

from backend.database import connection_scope
from backend.services.knowledge_profile_service import refresh_user_library_profile

REACTION_TYPES = {"like", "bookmark"}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def sanitize_visitor_id(visitor_id: str | None) -> str | None:
    if not visitor_id:
        return None
    text = visitor_id.strip()
    if not text or len(text) > 96:
        return None
    if not re.fullmatch(r"[a-zA-Z0-9:_-]+", text):
        return None
    return text


def _ensure_article_exists(connection, article_id: int) -> None:
    if connection.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Article not found")


def _sync_saved_article(connection, *, article_id: int, user_id: str, active: bool, timestamp: str) -> None:
    existing = connection.execute(
        "SELECT created_at FROM user_saved_articles WHERE user_id = ? AND article_id = ?",
        (user_id, article_id),
    ).fetchone()
    created_at = existing["created_at"] if existing is not None else timestamp
    connection.execute(
        """
        INSERT INTO user_saved_articles (
            user_id,
            article_id,
            saved_via,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, 'bookmark', ?, ?, ?)
        ON CONFLICT(user_id, article_id) DO UPDATE SET
            saved_via = excluded.saved_via,
            is_active = excluded.is_active,
            updated_at = excluded.updated_at
        """,
        (user_id, article_id, 1 if active else 0, created_at, timestamp),
    )


def _upsert_visitor(connection, visitor_id: str, user_id: str | None = None) -> None:
    timestamp = _now_iso()
    connection.execute(
        """
        INSERT INTO visitor_profiles (visitor_id, user_id, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(visitor_id) DO UPDATE SET
            user_id = COALESCE(excluded.user_id, visitor_profiles.user_id),
            last_seen_at = excluded.last_seen_at
        """,
        (visitor_id, user_id, timestamp, timestamp),
    )
    if user_id:
        connection.execute(
            """
            UPDATE article_view_events
            SET user_id = ?
            WHERE visitor_id = ? AND user_id IS NULL
            """,
            (user_id, visitor_id),
        )


def record_article_view(
    article_id: int,
    visitor_id: str | None,
    *,
    user_id: str | None = None,
    source: str = "article-detail",
) -> dict:
    safe_visitor_id = sanitize_visitor_id(visitor_id)
    if not safe_visitor_id:
        return {"recorded": False, "reason": "missing_visitor_id"}

    today = date.today().isoformat()
    timestamp = _now_iso()
    with connection_scope() as connection:
        _ensure_article_exists(connection, article_id)
        _upsert_visitor(connection, safe_visitor_id, user_id=user_id)
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO article_view_events (
                article_id, visitor_id, user_id, view_date, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (article_id, safe_visitor_id, user_id, today, source, timestamp),
        )
        recorded = cursor.rowcount > 0
        if recorded:
            connection.execute(
                """
                UPDATE articles
                SET view_count = COALESCE(view_count, 0) + 1,
                    updated_at = COALESCE(updated_at, ?)
                WHERE id = ?
                """,
                (timestamp, article_id),
            )
        connection.commit()
    return {"recorded": recorded, "view_date": today}


def fetch_article_engagement_map(connection, article_ids: list[int], user_id: str | None = None) -> dict[int, dict]:
    if not article_ids:
        return {}

    placeholders = ",".join("?" for _ in article_ids)
    article_rows = connection.execute(
        f"""
        SELECT id, COALESCE(view_count, 0) AS views
        FROM articles
        WHERE id IN ({placeholders})
        """,
        article_ids,
    ).fetchall()
    reaction_rows = connection.execute(
        f"""
        SELECT article_id, reaction_type, COUNT(*) AS total
        FROM article_reactions
        WHERE article_id IN ({placeholders}) AND is_active = 1
        GROUP BY article_id, reaction_type
        """,
        article_ids,
    ).fetchall()

    payload = {
        article_id: {
            "views": 0,
            "like_count": 0,
            "bookmark_count": 0,
            "liked_by_me": False,
            "bookmarked_by_me": False,
            "can_interact": bool(user_id),
        }
        for article_id in article_ids
    }

    for row in article_rows:
        payload[row["id"]]["views"] = row["views"]
    for row in reaction_rows:
        key = "like_count" if row["reaction_type"] == "like" else "bookmark_count"
        payload[row["article_id"]][key] = row["total"]

    if user_id:
        user_rows = connection.execute(
            f"""
            SELECT article_id, reaction_type
            FROM article_reactions
            WHERE article_id IN ({placeholders}) AND user_id = ? AND is_active = 1
            """,
            (*article_ids, user_id),
        ).fetchall()
        for row in user_rows:
            if row["reaction_type"] == "like":
                payload[row["article_id"]]["liked_by_me"] = True
            elif row["reaction_type"] == "bookmark":
                payload[row["article_id"]]["bookmarked_by_me"] = True

    return payload


def get_article_engagement(article_id: int, user_id: str | None = None) -> dict:
    with connection_scope() as connection:
        _ensure_article_exists(connection, article_id)
        payload = fetch_article_engagement_map(connection, [article_id], user_id=user_id)
        return payload.get(
            article_id,
            {
                "views": 0,
                "like_count": 0,
                "bookmark_count": 0,
                "liked_by_me": False,
                "bookmarked_by_me": False,
                "can_interact": bool(user_id),
            },
        )


def set_article_reaction(article_id: int, user_id: str, reaction_type: str, active: bool) -> dict:
    if reaction_type not in REACTION_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported reaction type")

    timestamp = _now_iso()
    with connection_scope() as connection:
        _ensure_article_exists(connection, article_id)
        connection.execute(
            """
            INSERT INTO article_reactions (
                article_id, user_id, reaction_type, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id, user_id, reaction_type) DO UPDATE SET
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
            """,
            (article_id, user_id, reaction_type, 1 if active else 0, timestamp, timestamp),
        )
        connection.commit()
        if reaction_type == "bookmark":
            _sync_saved_article(connection, article_id=article_id, user_id=user_id, active=active, timestamp=timestamp)
            connection.commit()
    if reaction_type == "bookmark":
        refresh_user_library_profile(user_id)
    return get_article_engagement(article_id, user_id=user_id)
