from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException

from backend.config import BUSINESS_DATA_DIR, COLUMN_DEFINITIONS, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from backend.database import connection_scope
from backend.services.article_ai_output_service import (
    build_current_article_source_hash,
    fetch_latest_article_ai_output_row,
    preview_markdown,
)
from backend.services.display_markdown_service import (
    cleanup_display_markdown,
    normalize_article_display_markdown,
    normalize_summary_display_markdown,
)
from backend.services.content_localization import (
    TAG_CATEGORY_LABELS,
    contains_cjk,
    english_article_ready,
    localize_column_payload,
    localize_tag_payload,
    localize_topic_payload,
)
from backend.services.engagement_service import fetch_article_engagement_map
from backend.services.fudan_wechat_renderer import is_fudan_wechat_preview_html
from backend.services.membership_service import build_content_access
from backend.services.article_visibility_service import is_hidden_low_value_article


def _organization_slug(name: str) -> str:
    lowered = (name or "").strip().lower()
    ascii_slug = re.sub(r"[^\w\s-]", "", lowered)
    ascii_slug = re.sub(r"[\s_]+", "-", ascii_slug).strip("-")
    if ascii_slug:
        return ascii_slug[:80]
    compact = re.sub(r"\s+", "", name or "")
    return compact[:40]


def article_cover_url(article_id: int, has_cover: bool) -> str | None:
    if not has_cover:
        return None
    return f"/api/article/{article_id}/cover"


def _fetch_tag_map(connection, article_ids: list[int]) -> dict[int, list[dict]]:
    if not article_ids:
        return {}
    placeholders = ",".join("?" for _ in article_ids)
    rows = connection.execute(
        f"""
        SELECT at.article_id, t.id, t.name, t.slug, t.category, t.color, t.article_count
        FROM article_tags at
        JOIN tags t ON t.id = at.tag_id
        WHERE at.article_id IN ({placeholders})
        ORDER BY
            CASE t.category
                WHEN 'industry' THEN 1
                WHEN 'topic' THEN 2
                WHEN 'type' THEN 3
                WHEN 'entity' THEN 4
                ELSE 5
            END,
            t.article_count DESC,
            t.name ASC
        """,
        article_ids,
    ).fetchall()
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["article_id"]].append(
            {
                "id": row["id"],
                "name": row["name"],
                "slug": row["slug"],
                "category": row["category"],
                "color": row["color"],
                "article_count": row["article_count"],
            }
        )
    return grouped


def _fetch_column_map(connection, article_ids: list[int]) -> dict[int, list[dict]]:
    if not article_ids:
        return {}
    placeholders = ",".join("?" for _ in article_ids)
    rows = connection.execute(
        f"""
        SELECT ac.article_id, c.id, c.name, c.slug, c.description, c.icon, c.accent_color
        FROM article_columns ac
        JOIN columns c ON c.id = ac.column_id
        WHERE ac.article_id IN ({placeholders})
        ORDER BY c.sort_order ASC, c.name ASC
        """,
        article_ids,
    ).fetchall()
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["article_id"]].append(
            {
                "id": row["id"],
                "name": row["name"],
                "slug": row["slug"],
                "description": row["description"],
                "icon": row["icon"],
                "accent_color": row["accent_color"],
                "article_count": 0,
            }
        )
    return grouped


def _fetch_access_map(connection, article_ids: list[int]) -> dict[int, str]:
    if not article_ids:
        return {}
    placeholders = ",".join("?" for _ in article_ids)
    rows = connection.execute(
        f"""
        SELECT id, COALESCE(access_level, 'public') AS access_level
        FROM articles
        WHERE id IN ({placeholders})
        """,
        article_ids,
    ).fetchall()
    return {row["id"]: row["access_level"] for row in rows}


def _preview_content(content: str, paragraph_limit: int = 4, char_limit: int = 900) -> str:
    return preview_markdown(content, paragraph_limit=paragraph_limit, char_limit=char_limit)


def _resolve_article_html(
    *,
    title: str,
    content_markdown: str,
    summary: str,
    source_url: str | None,
    stored_html: str | None,
) -> str | None:
    del title, content_markdown, summary, source_url
    html = str(stored_html or "").strip()
    if is_fudan_wechat_preview_html(html):
        return html
    return None


def _filter_visible_article_rows(connection, rows):
    if not rows:
        return []
    article_ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in article_ids)
    content_rows = connection.execute(
        f"""
        SELECT id, title, content
        FROM articles
        WHERE id IN ({placeholders})
        """,
        article_ids,
    ).fetchall()
    hidden_ids = {
        row["id"]
        for row in content_rows
        if is_hidden_low_value_article(row)
    }
    if not hidden_ids:
        return list(rows)
    return [row for row in rows if row["id"] not in hidden_ids]


def _fetch_translation_map(connection, article_ids: list[int], language: str) -> dict[int, dict[str, str]]:
    if language != "en" or not article_ids:
        return {}

    placeholders = ",".join("?" for _ in article_ids)
    source_rows = connection.execute(
        f"""
        SELECT
            id,
            title,
            excerpt,
            main_topic,
            content,
            COALESCE(access_level, 'public') AS access_level
        FROM articles
        WHERE id IN ({placeholders})
        """,
        article_ids,
    ).fetchall()
    current_hashes = {row["id"]: build_current_article_source_hash(row) for row in source_rows}

    translation_rows = connection.execute(
        f"""
        SELECT
            article_id,
            source_hash,
            title,
            excerpt,
            updated_at,
            created_at
        FROM article_translations
        WHERE article_id IN ({placeholders}) AND target_lang = 'en'
        ORDER BY article_id ASC, updated_at DESC, created_at DESC
        """,
        article_ids,
    ).fetchall()

    translation_map: dict[int, dict[str, str]] = {}
    for row in translation_rows:
        article_id = row["article_id"]
        if article_id in translation_map:
            continue
        if row["source_hash"] != current_hashes.get(article_id):
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
        SELECT
            article_id,
            source_hash,
            translation_title_en,
            translation_excerpt_en,
            updated_at
        FROM article_ai_outputs
        WHERE article_id IN ({fallback_placeholders})
          AND translation_status = 'completed'
          AND COALESCE(translation_content_en, '') != ''
        ORDER BY article_id ASC, updated_at DESC
        """,
        missing_ids,
    ).fetchall()

    for row in ai_rows:
        article_id = row["article_id"]
        if article_id in translation_map:
            continue
        if row["source_hash"] != current_hashes.get(article_id):
            continue
        translation_map[article_id] = {
            "title": str(row["translation_title_en"] or "").strip(),
            "excerpt": str(row["translation_excerpt_en"] or "").strip(),
        }

    return translation_map


def _serialize_articles(
    connection,
    rows,
    current_user_id: str | None = None,
    membership_profile: dict | None = None,
    language: str = "zh",
) -> list[dict]:
    rows = _filter_visible_article_rows(connection, rows)
    article_ids = [row["id"] for row in rows]
    tags_map = _fetch_tag_map(connection, article_ids)
    columns_map = _fetch_column_map(connection, article_ids)
    access_map = _fetch_access_map(connection, article_ids)
    translation_map = _fetch_translation_map(connection, article_ids, language)
    engagement_map = fetch_article_engagement_map(connection, article_ids, user_id=current_user_id)
    payload = []
    for row in rows:
        access = build_content_access(access_map.get(row["id"], "public"), membership_profile)
        engagement = engagement_map.get(
            row["id"],
            {
                "views": row["view_count"] or 0,
                "like_count": 0,
                "bookmark_count": 0,
                "liked_by_me": False,
                "bookmarked_by_me": False,
                "can_interact": bool(current_user_id),
            },
        )
        localized_title = translation_map.get(row["id"], {}).get("title") or row["title"]
        localized_excerpt = translation_map.get(row["id"], {}).get("excerpt") or row["excerpt"] or ""
        localized_main_topic = row["main_topic"]
        if language == "en" and contains_cjk(localized_main_topic):
            localized_main_topic = localized_excerpt or None
        localized_tags = []
        for tag in tags_map.get(row["id"], [])[:6]:
            localized = localize_tag_payload(tag, language=language)
            if localized:
                localized_tags.append(localized)
        localized_columns = [localize_column_payload(column, language=language) for column in columns_map.get(row["id"], [])]
        payload.append(
            {
                "id": row["id"],
                "title": localized_title,
                "slug": row["slug"],
                "publish_date": row["publish_date"],
                "source": row["source"],
                "excerpt": localized_excerpt,
                "article_type": row["article_type"],
                "main_topic": localized_main_topic,
                "access_level": access["access_level"],
                "access_label": access["access_label"],
                "view_count": engagement["views"] or row["view_count"] or 0,
                "like_count": engagement["like_count"],
                "bookmark_count": engagement["bookmark_count"],
                "cover_url": article_cover_url(row["id"], bool(row["cover_image_path"])),
                "link": row["link"],
                "tags": localized_tags,
                "columns": localized_columns,
                "score": row["score"] if "score" in row.keys() else None,
            }
        )
    return payload


def _take_language_ready_articles(items: list[dict], limit: int, language: str) -> list[dict]:
    if language != "en":
        return items[:limit]
    return [item for item in items if english_article_ready(item)][:limit]


def list_articles(
    *,
    order_by: str = "publish_date DESC",
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    where_sql: str = "",
    params: tuple = (),
    language: str = "zh",
) -> list[dict]:
    safe_limit = max(1, min(limit, MAX_PAGE_SIZE))
    with connection_scope() as connection:
        rows = connection.execute(
            f"""
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type, main_topic,
                view_count, cover_image_path, link
            FROM articles
            {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            (*params, safe_limit, offset),
        ).fetchall()
        items = _serialize_articles(connection, rows, language=language)
        return _take_language_ready_articles(items, safe_limit, language)


def get_article_detail(
    article_id: int,
    current_user_id: str | None = None,
    membership_profile: dict | None = None,
) -> dict:
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM articles
            WHERE id = ?
            """,
            (article_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Article not found")
        if is_hidden_low_value_article(row):
            raise HTTPException(status_code=404, detail="Article not found")

        article = _serialize_articles(
            connection,
            [row],
            current_user_id=current_user_id,
            membership_profile=membership_profile,
        )[0]
        access = build_content_access(row["access_level"] if "access_level" in row.keys() else "public", membership_profile)
        current_source_hash = build_current_article_source_hash(row)
        ai_row = fetch_latest_article_ai_output_row(connection, article_id, source_hash=current_source_hash)
        preferred_content = row["content"]
        summary_text = row["excerpt"] or row["main_topic"] or ""
        if ai_row is not None and ai_row["format_status"] == "completed" and str(ai_row["formatted_markdown_zh"] or "").strip():
            preferred_content = ai_row["formatted_markdown_zh"]
        if ai_row is not None and ai_row["summary_status"] == "completed" and str(ai_row["summary_zh"] or "").strip():
            summary_text = ai_row["summary_zh"]
        topic_rows = connection.execute(
            """
            SELECT t.id, t.title, t.slug, t.description, t.type, t.view_count, t.cover_article_id
            FROM topic_articles ta
            JOIN topics t ON t.id = ta.topic_id
            WHERE ta.article_id = ?
            ORDER BY t.updated_at DESC, t.title ASC
            """,
            (article_id,),
        ).fetchall()
        topics = []
        for topic_row in topic_rows:
            tags = connection.execute(
                """
                SELECT tg.id, tg.name, tg.slug, tg.category, tg.color, tg.article_count
                FROM topic_tags tt
                JOIN tags tg ON tg.id = tt.tag_id
                WHERE tt.topic_id = ?
                ORDER BY tg.article_count DESC, tg.name ASC
                """,
                (topic_row["id"],),
            ).fetchall()
            topics.append(
                {
                    "id": topic_row["id"],
                    "title": topic_row["title"],
                    "slug": topic_row["slug"],
                    "description": topic_row["description"],
                    "type": topic_row["type"],
                    "view_count": topic_row["view_count"] or 0,
                    "article_count": connection.execute(
                        "SELECT COUNT(*) FROM topic_articles WHERE topic_id = ?",
                        (topic_row["id"],),
                    ).fetchone()[0],
                    "cover_article_id": topic_row["cover_article_id"],
                    "cover_url": article_cover_url(
                        topic_row["cover_article_id"], bool(topic_row["cover_article_id"])
                    )
                    if topic_row["cover_article_id"]
                    else None,
                    "tags": [
                        {
                            "id": tag["id"],
                            "name": tag["name"],
                            "slug": tag["slug"],
                            "category": tag["category"],
                            "color": tag["color"],
                            "article_count": tag["article_count"],
                        }
                        for tag in tags
                    ],
                }
            )

        related_rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link,
                COUNT(*) AS score
            FROM article_tags current_tags
            JOIN article_tags other_tags ON other_tags.tag_id = current_tags.tag_id
            JOIN articles a ON a.id = other_tags.article_id
            WHERE current_tags.article_id = ? AND other_tags.article_id != ?
            GROUP BY a.id
            ORDER BY score DESC, a.publish_date DESC
            LIMIT 6
            """,
            (article_id, article_id),
        ).fetchall()

        visible_content = _preview_content(preferred_content) if access["locked"] else preferred_content
        visible_content = normalize_article_display_markdown(visible_content, "zh")
        summary_text = normalize_summary_display_markdown(summary_text, "zh")
        visible_html = _resolve_article_html(
            title=article["title"],
            content_markdown=visible_content,
            summary=summary_text,
            source_url=row["link"],
            stored_html=ai_row["html_wechat_zh"] if ai_row is not None else None,
        )

        detail = {
            **article,
            "content": visible_content,
            "html_web": visible_html,
            "html_wechat": visible_html,
            "relative_path": row["relative_path"],
            "source_mode": row["source_mode"],
            "primary_org_name": row["primary_org_name"],
            "series_or_column": row["series_or_column"],
            "word_count": row["word_count"] or 0,
            "access": access,
            "engagement": fetch_article_engagement_map(connection, [article_id], user_id=current_user_id).get(
                article_id,
                {
                    "views": article["view_count"] or 0,
                    "like_count": article["like_count"] or 0,
                    "bookmark_count": article["bookmark_count"] or 0,
                    "liked_by_me": False,
                    "bookmarked_by_me": False,
                    "can_interact": bool(current_user_id),
                },
            ),
            "topics": topics,
            "related_articles": _serialize_articles(
                connection,
                related_rows,
                current_user_id=current_user_id,
                membership_profile=membership_profile,
            ),
        }
        return detail


def increment_article_view_count(article_id: int) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE articles
            SET view_count = COALESCE(view_count, 0) + 1
            WHERE id = ?
            """,
            (article_id,),
        )
        connection.commit()


def get_article_cover_path(article_id: int) -> Path:
    with connection_scope() as connection:
        row = connection.execute(
            "SELECT cover_image_path FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    if row is None or not row["cover_image_path"]:
        raise HTTPException(status_code=404, detail="Cover not found")
    cover_path = (BUSINESS_DATA_DIR / row["cover_image_path"]).resolve()
    if not str(cover_path).startswith(str(BUSINESS_DATA_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid cover path")
    if not cover_path.exists():
        raise HTTPException(status_code=404, detail="Cover file missing")
    return cover_path


def list_columns() -> list[dict]:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id, c.name, c.slug, c.description, c.icon, c.accent_color,
                COUNT(ac.article_id) AS article_count
            FROM columns c
            LEFT JOIN article_columns ac ON ac.column_id = c.id
            GROUP BY c.id
            ORDER BY c.sort_order ASC, c.name ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_column_articles(slug: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (safe_page - 1) * safe_page_size
    with connection_scope() as connection:
        column = connection.execute(
            """
            SELECT id, name, slug, description, icon, accent_color
            FROM columns
            WHERE slug = ?
            """,
            (slug,),
        ).fetchone()
        if column is None:
            raise HTTPException(status_code=404, detail="Column not found")
        total = connection.execute(
            "SELECT COUNT(*) FROM article_columns WHERE column_id = ?",
            (column["id"],),
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM article_columns ac
            JOIN articles a ON a.id = ac.article_id
            WHERE ac.column_id = ?
            ORDER BY ac.is_featured DESC, a.publish_date DESC, a.view_count DESC
            LIMIT ? OFFSET ?
            """,
            (column["id"], safe_page_size, offset),
        ).fetchall()
        items = _serialize_articles(connection, rows)
    return {
        "column": {
            "id": column["id"],
            "name": column["name"],
            "slug": column["slug"],
            "description": column["description"],
            "icon": column["icon"],
            "accent_color": column["accent_color"],
            "article_count": total,
        },
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "items": items,
    }


def list_organizations(limit: int = 60) -> list[dict]:
    safe_limit = max(1, min(limit, 120))
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT primary_org_name, COUNT(*) AS article_count, MAX(publish_date) AS latest_publish_date
            FROM articles
            WHERE COALESCE(primary_org_name, '') != ''
            GROUP BY primary_org_name
            ORDER BY article_count DESC, latest_publish_date DESC, primary_org_name ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [
        {
            "name": row["primary_org_name"],
            "slug": _organization_slug(row["primary_org_name"]),
            "article_count": row["article_count"],
            "latest_publish_date": row["latest_publish_date"],
        }
        for row in rows
    ]


def get_organization_detail(slug: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (safe_page - 1) * safe_page_size

    organizations = list_organizations(limit=400)
    organization = next((item for item in organizations if item["slug"] == slug), None)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    with connection_scope() as connection:
        total = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM articles
            WHERE primary_org_name = ?
            """,
            (organization["name"],),
        ).fetchone()["total"]
        rows = connection.execute(
            """
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type,
                main_topic, view_count, cover_image_path, link
            FROM articles
            WHERE primary_org_name = ?
            ORDER BY publish_date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (organization["name"], safe_page_size, offset),
        ).fetchall()
        items = _serialize_articles(connection, rows)

    return {
        **organization,
        "page": safe_page,
        "page_size": safe_page_size,
        "articles": items,
    }


def list_tags() -> dict:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT id, name, slug, category, color, article_count
            FROM tags
            ORDER BY
                CASE category
                    WHEN 'industry' THEN 1
                    WHEN 'topic' THEN 2
                    WHEN 'type' THEN 3
                    WHEN 'entity' THEN 4
                    ELSE 5
                END,
                article_count DESC,
                name ASC
            """
        ).fetchall()
        hot = connection.execute(
            """
            SELECT id, name, slug, category, color, article_count
            FROM tags
            WHERE category IN ('topic', 'industry')
            ORDER BY article_count DESC, name ASC
            LIMIT 12
            """
        ).fetchall()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(dict(row))
    groups = [
        {
            "category": category,
            "label": TAG_CATEGORY_LABELS["zh"].get(category, category),
            "items": items[:24],
        }
        for category, items in grouped.items()
    ]
    return {"groups": groups, "hot": [dict(row) for row in hot]}


def get_tag_articles(tag_slug: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (safe_page - 1) * safe_page_size
    with connection_scope() as connection:
        tag = connection.execute(
            """
            SELECT id, name, slug, category, color, article_count
            FROM tags
            WHERE slug = ? OR name = ?
            """,
            (tag_slug, tag_slug),
        ).fetchone()
        if tag is None:
            raise HTTPException(status_code=404, detail="Tag not found")
        rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM article_tags at
            JOIN articles a ON a.id = at.article_id
            WHERE at.tag_id = ?
            ORDER BY a.publish_date DESC, a.view_count DESC
            LIMIT ? OFFSET ?
            """,
            (tag["id"], safe_page_size, offset),
        ).fetchall()
        items = _serialize_articles(connection, rows)
    return {
        "tag": dict(tag),
        "total": tag["article_count"],
        "page": safe_page,
        "page_size": safe_page_size,
        "items": items,
    }


def list_topics(language: str = "zh") -> list[dict]:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT id, title, slug, description, type, view_count, cover_article_id
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
        topic_ids = [row["id"] for row in rows]
        topic_tags: dict[int, list[dict]] = defaultdict(list)
        if topic_ids:
            placeholders = ",".join("?" for _ in topic_ids)
            tag_rows = connection.execute(
                f"""
                SELECT tt.topic_id, t.id, t.name, t.slug, t.category, t.color, t.article_count
                FROM topic_tags tt
                JOIN tags t ON t.id = tt.tag_id
                WHERE tt.topic_id IN ({placeholders})
                ORDER BY t.article_count DESC, t.name ASC
                """,
                topic_ids,
            ).fetchall()
            for row in tag_rows:
                topic_tags[row["topic_id"]].append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "slug": row["slug"],
                        "category": row["category"],
                        "color": row["color"],
                        "article_count": row["article_count"],
                    }
                )

        items = []
        for row in rows:
            article_count = connection.execute(
                "SELECT COUNT(*) FROM topic_articles WHERE topic_id = ?",
                (row["id"],),
            ).fetchone()[0]
            payload = localize_topic_payload(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "slug": row["slug"],
                    "description": row["description"],
                    "type": row["type"],
                    "view_count": row["view_count"] or 0,
                    "article_count": article_count,
                    "cover_article_id": row["cover_article_id"],
                    "cover_url": article_cover_url(
                        row["cover_article_id"], bool(row["cover_article_id"])
                    )
                    if row["cover_article_id"]
                    else None,
                    "tags": topic_tags.get(row["id"], []),
                },
                language=language,
            )
            items.append(payload)
        return items


def increment_topic_view_count_by_slug(slug: str) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE topics
            SET view_count = COALESCE(view_count, 0) + 1
            WHERE slug = ?
            """,
            (slug,),
        )
        connection.commit()


def get_topic_detail(slug: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (safe_page - 1) * safe_page_size
    with connection_scope() as connection:
        topic = connection.execute(
            """
            SELECT id, title, slug, description, type, view_count, cover_article_id
            FROM topics
            WHERE slug = ? AND status = 'published'
            """,
            (slug,),
        ).fetchone()
        if topic is None:
            raise HTTPException(status_code=404, detail="Topic not found")

        tag_rows = connection.execute(
            """
            SELECT t.id, t.name, t.slug, t.category, t.color, t.article_count
            FROM topic_tags tt
            JOIN tags t ON t.id = tt.tag_id
            WHERE tt.topic_id = ?
            ORDER BY t.article_count DESC, t.name ASC
            """,
            (topic["id"],),
        ).fetchall()

        total = connection.execute(
            "SELECT COUNT(*) FROM topic_articles WHERE topic_id = ?",
            (topic["id"],),
        ).fetchone()[0]

        article_rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM topic_articles ta
            JOIN articles a ON a.id = ta.article_id
            WHERE ta.topic_id = ?
            ORDER BY ta.sort_order ASC, a.publish_date DESC
            LIMIT ? OFFSET ?
            """,
            (topic["id"], safe_page_size, offset),
        ).fetchall()

        timeline_rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.publish_date, a.excerpt
            FROM topic_articles ta
            JOIN articles a ON a.id = ta.article_id
            WHERE ta.topic_id = ?
            ORDER BY ta.sort_order ASC, a.publish_date DESC
            LIMIT 12
            """,
            (topic["id"],),
        ).fetchall()

        date_span = connection.execute(
            """
            SELECT MIN(a.publish_date) AS first_date, MAX(a.publish_date) AS last_date
            FROM topic_articles ta
            JOIN articles a ON a.id = ta.article_id
            WHERE ta.topic_id = ?
            """,
            (topic["id"],),
        ).fetchone()

        articles = _serialize_articles(connection, article_rows)
        timeline = [
            {
                "article_id": row["id"],
                "date": row["publish_date"],
                "title": row["title"],
                "excerpt": row["excerpt"][:120],
            }
            for row in timeline_rows
        ]
        insights = []
        if total:
            top_tags = [row["name"] for row in tag_rows[:4]]
            first_date = date_span["first_date"]
            last_date = date_span["last_date"]
            insights = [
                f"本专题共收录 {total} 篇相关文章，时间跨度从 {first_date} 到 {last_date}。",
                f"高频视角集中在 {', '.join(top_tags)}。",
                "优先推荐阅读近年的长文、访谈与案例文章，以把握该主题的最新演进。",
            ]

        return {
            "id": topic["id"],
            "title": topic["title"],
            "slug": topic["slug"],
            "description": topic["description"],
            "type": topic["type"],
            "view_count": topic["view_count"] or 0,
            "article_count": total,
            "cover_article_id": topic["cover_article_id"],
            "cover_url": article_cover_url(topic["cover_article_id"], bool(topic["cover_article_id"]))
            if topic["cover_article_id"]
            else None,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "tags": [dict(row) for row in tag_rows],
            "timeline": timeline,
            "insights": insights,
            "articles": articles,
        }


def get_topic_timeline(topic_id: int) -> dict:
    with connection_scope() as connection:
        topic = connection.execute(
            """
            SELECT id, title, slug
            FROM topics
            WHERE id = ? AND status = 'published'
            """,
            (topic_id,),
        ).fetchone()
        if topic is None:
            raise HTTPException(status_code=404, detail="Topic not found")
    detail = get_topic_detail(topic["slug"], page=1, page_size=1)
    return {
        "topic_id": topic["id"],
        "slug": topic["slug"],
        "title": topic["title"],
        "timeline": detail["timeline"],
    }


def get_topic_insights(topic_id: int) -> dict:
    with connection_scope() as connection:
        topic = connection.execute(
            """
            SELECT id, title, slug
            FROM topics
            WHERE id = ? AND status = 'published'
            """,
            (topic_id,),
        ).fetchone()
        if topic is None:
            raise HTTPException(status_code=404, detail="Topic not found")
    detail = get_topic_detail(topic["slug"], page=1, page_size=1)
    return {
        "topic_id": topic["id"],
        "slug": topic["slug"],
        "title": topic["title"],
        "insights": detail["insights"],
    }


def get_home_feed(language: str = "zh") -> dict:
    with connection_scope() as connection:
        hero_row = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM featured_articles fa
            JOIN articles a ON a.id = fa.article_id
            WHERE fa.position = 'hero' AND fa.is_active = 1
            ORDER BY fa.id DESC
            LIMIT 1
            """
        ).fetchone()
        pick_rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM featured_articles fa
            JOIN articles a ON a.id = fa.article_id
            WHERE fa.position LIKE 'editor-%' AND fa.is_active = 1
            ORDER BY fa.position ASC
            LIMIT ?
            """
        , (12 if language == "en" else 6,)).fetchall()
        trending_rows = connection.execute(
            """
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type,
                main_topic, view_count, cover_image_path, link
            FROM articles
            ORDER BY (
                COALESCE(view_count, 0)
                + 4 * (
                    SELECT COUNT(*)
                    FROM article_reactions ar
                    WHERE ar.article_id = articles.id
                      AND ar.reaction_type = 'like'
                      AND ar.is_active = 1
                )
                + 6 * (
                    SELECT COUNT(*)
                    FROM article_reactions ar
                    WHERE ar.article_id = articles.id
                      AND ar.reaction_type = 'bookmark'
                      AND ar.is_active = 1
                )
            ) DESC,
            publish_date DESC,
            id DESC
            LIMIT ?
            """
        , (18 if language == "en" else 6,)).fetchall()
        latest_rows = connection.execute(
            """
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type,
                main_topic, view_count, cover_image_path, link
            FROM articles
            ORDER BY publish_date DESC, id DESC
            LIMIT ?
            """
        , (24 if language == "en" else 12,)).fetchall()
        hot_tags = connection.execute(
            """
            SELECT id, name, slug, category, color, article_count
            FROM tags
            WHERE category IN ('topic', 'industry')
            ORDER BY article_count DESC, name ASC
            LIMIT 10
            """
        ).fetchall()

        column_previews = []
        for column in COLUMN_DEFINITIONS:
            rows = connection.execute(
                """
                SELECT
                    a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                    a.main_topic, a.view_count, a.cover_image_path, a.link
                FROM article_columns ac
                JOIN columns c ON c.id = ac.column_id
                JOIN articles a ON a.id = ac.article_id
                WHERE c.slug = ?
                ORDER BY ac.is_featured DESC, a.publish_date DESC
                LIMIT ?
                """,
                (column["slug"], 8 if language == "en" else 3),
            ).fetchall()
            localized_items = _take_language_ready_articles(
                _serialize_articles(connection, rows, language=language),
                3,
                language,
            )
            column_previews.append(
                {
                    "column": localize_column_payload(
                        {
                        "id": 0,
                        "name": column["name"],
                        "slug": column["slug"],
                        "description": column["description"],
                        "icon": column["icon"],
                        "accent_color": column["accent_color"],
                        "article_count": connection.execute(
                            """
                            SELECT COUNT(*)
                            FROM article_columns ac
                            JOIN columns c ON c.id = ac.column_id
                            WHERE c.slug = ?
                            """,
                            (column["slug"],),
                        ).fetchone()[0],
                    },
                        language=language,
                    ),
                    "items": localized_items,
                }
            )

        hero_item = None
        if hero_row:
            hero_items = _serialize_articles(connection, [hero_row], language=language)
            if hero_items:
                candidate = hero_items[0]
                if language != "en" or english_article_ready(candidate):
                    hero_item = candidate

        serialized_picks = _serialize_articles(connection, pick_rows, language=language)
        serialized_trending = _serialize_articles(connection, trending_rows, language=language)
        serialized_latest = _serialize_articles(connection, latest_rows, language=language)

        if hero_item is None and language == "en":
            hero_item = next(
                (
                    item
                    for item in [*serialized_picks, *serialized_trending, *serialized_latest]
                    if english_article_ready(item)
                ),
                None,
            )

        localized_hot_tags = []
        for row in hot_tags:
            localized = localize_tag_payload(dict(row), language=language)
            if localized:
                localized_hot_tags.append(localized)

        topics = list_topics(language=language)[:4]
        return {
            "hero": hero_item,
            "editors_picks": _take_language_ready_articles(serialized_picks, 6, language),
            "trending": _take_language_ready_articles(serialized_trending, 6, language),
            "column_previews": column_previews,
            "latest": _take_language_ready_articles(serialized_latest, 12, language),
            "hot_tags": localized_hot_tags[:10],
            "topics": topics,
        }


def store_chat_session(session_id: str, title: str, last_question: str) -> None:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO chat_sessions (id, title, created_at, updated_at, last_question)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                last_question = excluded.last_question
            """,
            (session_id, title, timestamp, timestamp, last_question),
        )
        connection.commit()


def append_chat_message(
    session_id: str,
    role: str,
    content: str,
    sources: list[dict] | None = None,
    follow_ups: list[str] | None = None,
) -> None:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO chat_messages (session_id, role, content, sources_json, follow_ups_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(sources or [], ensure_ascii=False),
                json.dumps(follow_ups or [], ensure_ascii=False),
                timestamp,
            ),
        )
        connection.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (timestamp, session_id),
        )
        connection.commit()


def list_chat_sessions() -> list[dict]:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT id, title, updated_at, last_question
            FROM chat_sessions
            ORDER BY updated_at DESC
            LIMIT 30
            """
        ).fetchall()
    return [
        {
            "session_id": row["id"],
            "title": row["title"],
            "updated_at": row["updated_at"],
            "last_question": row["last_question"],
        }
        for row in rows
    ]


def get_chat_session_detail(session_id: str) -> dict:
    with connection_scope() as connection:
        session = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        rows = connection.execute(
            """
            SELECT role, content, sources_json, follow_ups_json, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    messages = []
    for row in rows:
        messages.append(
            {
                "role": row["role"],
                "content": row["content"],
                "sources": json.loads(row["sources_json"] or "[]"),
                "follow_ups": json.loads(row["follow_ups_json"] or "[]"),
                "created_at": row["created_at"],
            }
        )
    return {
        "session_id": session["id"],
        "title": session["title"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "messages": messages,
    }


def delete_chat_session(session_id: str) -> dict:
    with connection_scope() as connection:
        session = connection.execute(
            """
            SELECT id
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")

        connection.execute(
            """
            DELETE FROM chat_messages
            WHERE session_id = ?
            """,
            (session_id,),
        )
        connection.execute(
            """
            DELETE FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        )
        connection.commit()

    return {
        "session_id": session_id,
        "deleted": True,
    }


_NON_COMMERCIAL_ARTICLE_PATTERN = re.compile(r"(?:\bsmoke\b|\btest\b|\bdemo\b|\beditorial\b|\u6d4b\u8bd5|\u6f14\u793a|\u5192\u70df)", re.IGNORECASE)


def _pick_quote(content: str) -> str:
    paragraphs = [part.strip() for part in str(content or "").splitlines() if part.strip()]
    for paragraph in paragraphs:
        if 18 <= len(paragraph) <= 120:
            return paragraph
    if paragraphs:
        first_paragraph = re.sub(r"\s+", " ", paragraphs[0]).strip()
        if len(first_paragraph) <= 120:
            return first_paragraph
        clipped = first_paragraph[:120]
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        return clipped.rstrip(",;:-") + "..."
    return "Find a clearer judgment inside business change."


def _is_commercial_safe_article(row: dict) -> bool:
    source = str(row.get("source") or "").strip().lower()
    if source == "editorial":
        return False
    haystack = " ".join(
        [
            str(row.get("title") or ""),
            str(row.get("slug") or ""),
            str(row.get("excerpt") or ""),
            str(row.get("main_topic") or ""),
            source,
        ]
    )
    return _NON_COMMERCIAL_ARTICLE_PATTERN.search(haystack) is None


def _safe_iso_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _current_local_datetime() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _current_local_date() -> date:
    return _current_local_datetime().date()


def _article_age_days(row: dict, anchor_date: date) -> int:
    published = _safe_iso_date(row.get("publish_date"))
    if published is None:
        return 3650
    return max((anchor_date - published).days, 0)


def _daily_read_priority(row: dict, anchor_date: date) -> float:
    age_days = _article_age_days(row, anchor_date)
    freshness = max(0.0, 180 - age_days) / 18
    popularity = min((row.get("view_count") or 0) / 1800, 3.4)
    feature_boost = 2.2 if row.get("is_featured") else 0.0
    depth_boost = min((row.get("word_count") or 0) / 2600, 1.4)
    return round(freshness + popularity + feature_boost + depth_boost, 4)


def _daily_rotation_index(anchor_date: date, size: int) -> int:
    if size <= 1:
        return 0
    digest = hashlib.sha1(anchor_date.isoformat().encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % size


def _serialize_safe_article_cards(connection, rows, *, language: str, limit: int) -> list[dict]:
    safe_rows = [row for row in rows if _is_commercial_safe_article(dict(row))]
    if not safe_rows:
        return []
    items = _serialize_articles(connection, safe_rows, language=language)
    if language == "en":
        items = [item for item in items if english_article_ready(item)]
    return items[:limit]


def _load_context_source_ids(connection, session_id: str | None) -> list[int]:
    if not session_id:
        return []

    rows = connection.execute(
        """
        SELECT sources_json
        FROM chat_messages
        WHERE session_id = ? AND role = 'assistant'
        ORDER BY id DESC
        LIMIT 8
        """,
        (session_id,),
    ).fetchall()
    source_ids: list[int] = []
    seen_ids: set[int] = set()
    for row in rows:
        for source in json.loads(row["sources_json"] or "[]"):
            article_id = source.get("id")
            if isinstance(article_id, int) and article_id not in seen_ids:
                seen_ids.add(article_id)
                source_ids.append(article_id)
    return source_ids


def _get_high_signal_rows(connection, *, anchor_date: date, limit: int):
    safe_limit = max(1, min(limit, MAX_PAGE_SIZE))
    raw_rows = connection.execute(
        """
        SELECT
            id, title, slug, publish_date, source, excerpt, article_type,
            main_topic, view_count, cover_image_path, link, word_count, is_featured
        FROM articles
        WHERE publish_date <= ?
        ORDER BY is_featured DESC, publish_date DESC, view_count DESC, word_count DESC, id DESC
        LIMIT ?
        """,
        (anchor_date.isoformat(), safe_limit * 18),
    ).fetchall()
    safe_rows = [row for row in raw_rows if _is_commercial_safe_article(dict(row))]
    if not safe_rows:
        return []

    recent_cutoff = (anchor_date - timedelta(days=180)).isoformat()
    recent_rows = [row for row in safe_rows if str(row["publish_date"] or "") >= recent_cutoff]
    return recent_rows or safe_rows


def get_daily_read(target_date: str | None = None, language: str = "zh") -> dict:
    normalized_language = "en" if language == "en" else "zh"
    current_moment = _current_local_datetime()
    anchor_date = _safe_iso_date(target_date) or current_moment.date()

    with connection_scope() as connection:
        raw_rows = connection.execute(
            """
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type,
                main_topic, view_count, cover_image_path, link, word_count, is_featured
            FROM articles
            WHERE publish_date <= ?
            ORDER BY publish_date DESC, view_count DESC, id DESC
            LIMIT 240
            """,
            (anchor_date.isoformat(),),
        ).fetchall()

        safe_rows = [row for row in raw_rows if _is_commercial_safe_article(dict(row))]
        if not safe_rows:
            raise HTTPException(status_code=404, detail="No article found")

        recent_rows = [row for row in safe_rows if _article_age_days(dict(row), anchor_date) <= 180]
        candidate_rows = recent_rows or safe_rows[:96]
        ranked_rows = sorted(
            candidate_rows,
            key=lambda row: (
                _daily_read_priority(dict(row), anchor_date),
                row["publish_date"],
                row["view_count"] or 0,
                row["id"],
            ),
            reverse=True,
        )[:12]
        items = _serialize_safe_article_cards(connection, ranked_rows, language=normalized_language, limit=len(ranked_rows))
        if not items:
            items = _serialize_safe_article_cards(connection, candidate_rows, language=normalized_language, limit=24)
        if not items:
            raise HTTPException(status_code=404, detail="No article found")

    item = items[_daily_rotation_index(anchor_date, len(items))]
    quote_source = item["excerpt"] if normalized_language == "en" else item.get("excerpt") or item["title"]
    return {
        **item,
        "reading_date": anchor_date.isoformat(),
        "quote": _pick_quote(quote_source) or item["title"],
        "selection_window_days": 180,
        "generated_at": current_moment.isoformat(),
        "timezone": current_moment.tzname() or "local",
    }


def get_time_machine(target_date: str | None = None, language: str = "zh") -> dict:
    normalized_language = "en" if language == "en" else "zh"
    with connection_scope() as connection:
        if target_date:
            candidate_rows = connection.execute(
                """
                SELECT *
                FROM articles
                ORDER BY ABS(JULIANDAY(publish_date) - JULIANDAY(?)) ASC, view_count DESC, id DESC
                LIMIT 96
                """,
                (target_date,),
            ).fetchall()
        else:
            candidate_rows = connection.execute(
                """
                SELECT *
                FROM articles
                ORDER BY publish_date DESC, view_count DESC, id DESC
                LIMIT 96
                """
            ).fetchall()

        safe_rows = [row for row in candidate_rows if _is_commercial_safe_article(dict(row))]
        if not safe_rows:
            raise HTTPException(status_code=404, detail="No article found")

        serialized = _serialize_articles(connection, safe_rows, language=normalized_language)
        if normalized_language == "en":
            serialized = [item for item in serialized if english_article_ready(item)]
        if not serialized:
            raise HTTPException(status_code=404, detail="No article found")

        item = serialized[0]

    quote_source = item["excerpt"] if normalized_language == "en" else item.get("excerpt") or item["title"]
    quote = _pick_quote(quote_source) or item["title"]
    return {
        "id": item["id"],
        "title": item["title"],
        "publish_date": item["publish_date"],
        "quote": quote,
        "excerpt": item["excerpt"],
        "cover_url": item["cover_url"],
    }


def get_recommended_articles(session_id: str | None = None, limit: int = 5, language: str = "zh") -> dict:
    normalized_language = "en" if language == "en" else "zh"
    safe_limit = max(1, min(limit, MAX_PAGE_SIZE))
    anchor_date = _current_local_date()
    with connection_scope() as connection:
        source_ids = _load_context_source_ids(connection, session_id)

        if source_ids:
            source_placeholders = ",".join("?" for _ in source_ids)
            rows = connection.execute(
                f"""
                SELECT
                    a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                    a.main_topic, a.view_count, a.cover_image_path, a.link, a.word_count, a.is_featured,
                    COUNT(*) AS recommendation_score
                FROM article_tags current_tags
                JOIN article_tags other_tags ON other_tags.tag_id = current_tags.tag_id
                JOIN articles a ON a.id = other_tags.article_id
                WHERE current_tags.article_id IN ({source_placeholders})
                  AND other_tags.article_id NOT IN ({source_placeholders})
                GROUP BY a.id
                ORDER BY recommendation_score DESC, a.view_count DESC, a.publish_date DESC
                LIMIT ?
                """,
                (*source_ids, *source_ids, safe_limit * 8),
            ).fetchall()
            items = _serialize_safe_article_cards(connection, rows, language=normalized_language, limit=safe_limit)
            if items:
                return {
                    "items": items,
                    "mode": "contextual",
                    "source_count": len(source_ids),
                }

        fallback_rows = _get_high_signal_rows(connection, anchor_date=anchor_date, limit=safe_limit)
        fallback_items = _serialize_safe_article_cards(connection, fallback_rows, language=normalized_language, limit=safe_limit)
        return {
            "items": fallback_items,
            "mode": "high_signal",
            "source_count": len(source_ids),
        }
