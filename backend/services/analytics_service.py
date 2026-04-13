from __future__ import annotations

from datetime import date, timedelta

from backend.database import connection_scope
from backend.services.catalog_service import _serialize_articles


def get_analytics_overview() -> dict:
    with connection_scope() as connection:
        total_views = connection.execute("SELECT COALESCE(SUM(view_count), 0) FROM articles").fetchone()[0]
        total_likes = connection.execute(
            """
            SELECT COUNT(*)
            FROM article_reactions
            WHERE reaction_type = 'like' AND is_active = 1
            """
        ).fetchone()[0]
        total_bookmarks = connection.execute(
            """
            SELECT COUNT(*)
            FROM article_reactions
            WHERE reaction_type = 'bookmark' AND is_active = 1
            """
        ).fetchone()[0]

        seven_days_ago = (date.today() - timedelta(days=6)).isoformat()
        unique_visitors = connection.execute(
            """
            SELECT COUNT(DISTINCT visitor_id)
            FROM article_view_events
            WHERE view_date >= ?
            """,
            (seven_days_ago,),
        ).fetchone()[0]

        trend_rows = connection.execute(
            """
            SELECT view_date, COUNT(*) AS total
            FROM article_view_events
            WHERE view_date >= ?
            GROUP BY view_date
            ORDER BY view_date ASC
            """,
            (seven_days_ago,),
        ).fetchall()
        trend_map = {row["view_date"]: row["total"] for row in trend_rows}
        views_trend = []
        for offset in range(7):
            current = date.today() - timedelta(days=6 - offset)
            key = current.isoformat()
            views_trend.append({"label": current.strftime("%m-%d"), "value": int(trend_map.get(key, 0))})

        viewed_rows = connection.execute(
            """
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type,
                main_topic, view_count, cover_image_path, link
            FROM articles
            ORDER BY view_count DESC, publish_date DESC, id DESC
            LIMIT 6
            """
        ).fetchall()
        liked_rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link,
                COUNT(*) AS score
            FROM article_reactions ar
            JOIN articles a ON a.id = ar.article_id
            WHERE ar.reaction_type = 'like' AND ar.is_active = 1
            GROUP BY a.id
            ORDER BY score DESC, a.view_count DESC, a.publish_date DESC
            LIMIT 6
            """
        ).fetchall()
        bookmarked_rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link,
                COUNT(*) AS score
            FROM article_reactions ar
            JOIN articles a ON a.id = ar.article_id
            WHERE ar.reaction_type = 'bookmark' AND ar.is_active = 1
            GROUP BY a.id
            ORDER BY score DESC, a.view_count DESC, a.publish_date DESC
            LIMIT 6
            """
        ).fetchall()

        return {
            "metrics": [
                {"label": "累计浏览", "value": str(total_views), "detail": "文章聚合浏览量"},
                {"label": "累计点赞", "value": str(total_likes), "detail": "登录用户点赞总数"},
                {"label": "累计收藏", "value": str(total_bookmarks), "detail": "登录用户收藏总数"},
                {"label": "7日访客", "value": str(unique_visitors), "detail": "最近 7 天去重访客数"},
            ],
            "views_trend": views_trend,
            "top_viewed": _serialize_articles(connection, viewed_rows),
            "top_liked": _serialize_articles(connection, liked_rows),
            "top_bookmarked": _serialize_articles(connection, bookmarked_rows),
        }
