from __future__ import annotations

from backend.database import connection_scope
from backend.services.catalog_service import _serialize_articles


def _fetch_articles_for_reaction(user_id: str, reaction_type: str, limit: int):
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM article_reactions ar
            JOIN articles a ON a.id = ar.article_id
            WHERE ar.user_id = ? AND ar.reaction_type = ? AND ar.is_active = 1
            ORDER BY ar.updated_at DESC, ar.id DESC
            LIMIT ?
            """,
            (user_id, reaction_type, limit),
        ).fetchall()
        return _serialize_articles(connection, rows, current_user_id=user_id)


def _fetch_recent_views(user_id: str, limit: int):
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link,
                MAX(ave.created_at) AS last_viewed_at
            FROM article_view_events ave
            JOIN articles a ON a.id = ave.article_id
            WHERE ave.user_id = ?
            GROUP BY a.id
            ORDER BY last_viewed_at DESC, a.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return _serialize_articles(connection, rows, current_user_id=user_id)


def get_user_library(user_id: str, limit: int = 12) -> dict:
    safe_limit = max(1, min(limit, 30))
    return {
        "bookmarks": _fetch_articles_for_reaction(user_id, "bookmark", safe_limit),
        "likes": _fetch_articles_for_reaction(user_id, "like", safe_limit),
        "recent_views": _fetch_recent_views(user_id, safe_limit),
    }
