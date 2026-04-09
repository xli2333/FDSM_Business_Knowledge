from __future__ import annotations

import hashlib
from collections import Counter

from backend.database import connection_scope
from backend.scripts.build_business_db import (
    COLOR_BY_CATEGORY,
    load_ai_output,
    slugify,
)
from backend.services.rag_engine import refresh_search_cache
from backend.services.taxonomy_service import KEYWORD_STOPWORDS, build_tag_entries, normalize_keyword


def _build_allowed_keywords(ai_map: dict[str, dict]) -> set[str]:
    keyword_counter: Counter[str] = Counter()
    for item in ai_map.values():
        model = item.get("model_output") or {}
        for keyword in (model.get("topic_keywords") or [])[:5]:
            normalized = normalize_keyword(keyword)
            if normalized:
                keyword_counter[normalized] += 1
        normalized_topic = normalize_keyword(str(model.get("main_topic") or ""))
        if normalized_topic:
            keyword_counter[normalized_topic] += 1
    return {
        keyword
        for keyword, count in keyword_counter.items()
        if count >= 6 and keyword not in KEYWORD_STOPWORDS and len(keyword) <= 18
    }


def _build_strong_series(ai_map: dict[str, dict]) -> set[str]:
    series_counter: Counter[str] = Counter()
    for item in ai_map.values():
        model = item.get("model_output") or {}
        series = str(model.get("series_or_column") or "").strip()
        if series:
            series_counter[series] += 1
    return {series for series, count in series_counter.items() if count >= 8}


def _derive_tag_entries(
    row: dict,
    known_categories: dict[str, str],
    *,
    allowed_keywords: set[str] | None = None,
    strong_series: set[str] | None = None,
    ai_row: dict | None = None,
) -> list[tuple[str, str, float]]:
    model = (ai_row or {}).get("model_output") or {}
    raw_keywords: list[str] = []
    for keyword in (model.get("topic_keywords") or [])[:5]:
        normalized = normalize_keyword(str(keyword))
        if normalized:
            raw_keywords.append(normalized)
    if row.get("main_topic"):
        raw_keywords.append(str(row["main_topic"]))
    elif model.get("main_topic"):
        raw_keywords.append(str(model["main_topic"]))

    people_names = [item.strip() for item in (row.get("people_text") or "").split(" | ") if item.strip()]
    if not people_names:
        for item in model.get("people") or []:
            person_name = str(item.get("person_name") or "").strip()
            if person_name:
                people_names.append(person_name)

    org_names = [item.strip() for item in (row.get("org_text") or "").split(" | ") if item.strip()]
    if not org_names:
        primary_org = str(model.get("primary_org_name") or "").strip()
        if primary_org:
            org_names.append(primary_org)
        for item in model.get("people") or []:
            org_name = str(item.get("org_name") or "").strip()
            if org_name:
                org_names.append(org_name)

    return build_tag_entries(
        title=row.get("title") or "",
        main_topic=row.get("main_topic"),
        excerpt=row.get("excerpt") or "",
        content=row.get("content") or "",
        article_type=row.get("article_type"),
        series_or_column=row.get("series_or_column"),
        raw_keywords=raw_keywords,
        people_names=people_names,
        org_names=org_names,
        allowed_keywords=allowed_keywords,
        strong_series=strong_series,
        known_categories=known_categories,
    )


def _ensure_tag(connection, name: str, category: str) -> int:
    row = connection.execute(
        """
        SELECT id
        FROM tags
        WHERE name = ? AND category = ?
        """,
        (name, category),
    ).fetchone()
    if row is not None:
        return row["id"]

    base_slug = slugify(f"{category}-{name}")[:80]
    slug = base_slug
    suffix = 1
    while connection.execute("SELECT 1 FROM tags WHERE slug = ?", (slug,)).fetchone():
        digest = hashlib.sha1(f"{category}:{name}:{suffix}".encode("utf-8")).hexdigest()[:8]
        slug = f"{base_slug[:71]}-{digest}"
        suffix += 1

    connection.execute(
        """
        INSERT INTO tags (name, slug, category, description, color, article_count)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            name,
            slug,
            category,
            f"{name} 相关文章聚合标签",
            COLOR_BY_CATEGORY.get(category, "#64748b"),
        ),
    )
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def generate_tags_for_articles(limit: int = 50, regenerate: bool = False, source: str | None = None) -> dict:
    safe_limit = max(1, min(limit, 5000))
    source_value = (source or "").strip()
    ai_map = load_ai_output()
    allowed_keywords = _build_allowed_keywords(ai_map)
    strong_series = _build_strong_series(ai_map)
    with connection_scope() as connection:
        known_categories = {
            row["name"]: row["category"]
            for row in connection.execute("SELECT name, category FROM tags").fetchall()
        }
        where_sql = "WHERE source = ?" if source_value else ""
        params: tuple[object, ...]
        if regenerate:
            params = (source_value, safe_limit) if source_value else (safe_limit,)
            rows = connection.execute(
                f"""
                SELECT *
                FROM articles
                {where_sql}
                ORDER BY publish_date DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        else:
            params = (source_value, safe_limit) if source_value else (safe_limit,)
            rows = connection.execute(
                f"""
                SELECT a.*
                FROM articles a
                LEFT JOIN article_tags at ON at.article_id = a.id
                {where_sql.replace("source", "a.source")}
                GROUP BY a.id
                HAVING COUNT(at.tag_id) = 0
                ORDER BY a.publish_date DESC, a.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        processed_articles = []
        created_tags = 0
        for row in rows:
            article = dict(row)
            if regenerate:
                connection.execute("DELETE FROM article_tags WHERE article_id = ?", (article["id"],))
            ai_row = ai_map.get(article.get("relative_path") or "") if article.get("source") == "business" else None
            tag_entries = _derive_tag_entries(
                article,
                known_categories,
                allowed_keywords=allowed_keywords if article.get("source") == "business" else None,
                strong_series=strong_series if article.get("source") == "business" else None,
                ai_row=ai_row,
            )
            topic_tag_names = [name for name, category, _ in tag_entries if category in {"topic", "industry", "type", "series"}]
            connection.execute(
                """
                UPDATE articles
                SET tag_text = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (" | ".join(topic_tag_names), article["id"]),
            )
            for name, category, confidence in tag_entries:
                tag_id_before = connection.execute(
                    "SELECT id FROM tags WHERE name = ? AND category = ?",
                    (name, category),
                ).fetchone()
                tag_id = _ensure_tag(connection, name, category)
                if tag_id_before is None:
                    created_tags += 1
                    known_categories[name] = category
                connection.execute(
                    """
                    INSERT OR REPLACE INTO article_tags (article_id, tag_id, confidence)
                    VALUES (?, ?, ?)
                    """,
                    (article["id"], tag_id, confidence),
                )
            processed_articles.append(article["id"])

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
        connection.commit()

    refresh_search_cache()
    return {
        "processed_count": len(processed_articles),
        "processed_article_ids": processed_articles,
        "created_tag_count": created_tags,
        "regenerate": regenerate,
        "source": source_value or None,
    }
