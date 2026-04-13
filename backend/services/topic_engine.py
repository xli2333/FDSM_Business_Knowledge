from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime

from backend.config import TOPIC_AUTO_CLUSTERS, TOPIC_SEEDS
from backend.database import connection_scope


def _unique_topic_slug(connection, base_slug: str) -> str:
    slug = base_slug
    suffix = 1
    while connection.execute("SELECT 1 FROM topics WHERE slug = ?", (slug,)).fetchone():
        digest = hashlib.sha1(f"{base_slug}:{suffix}".encode("utf-8")).hexdigest()[:8]
        slug = f"{base_slug[:70]}-{digest}"
        suffix += 1
    return slug


def _primary_tags(seed: dict) -> set[str]:
    values = seed.get("primary_tags") or seed.get("match_tags") or []
    return {str(item).strip() for item in values if str(item).strip()}


def _support_tags(seed: dict) -> set[str]:
    values = seed.get("support_tags") or []
    return {str(item).strip() for item in values if str(item).strip()}


def _all_seed_tags(seed: dict) -> set[str]:
    return _primary_tags(seed) | _support_tags(seed)


def _cluster_required_tags(cluster: dict) -> set[str]:
    values = cluster.get("required_tags") or []
    return {str(item).strip() for item in values if str(item).strip()}


def _cluster_support_tags(cluster: dict) -> set[str]:
    values = cluster.get("support_tags") or []
    return {str(item).strip() for item in values if str(item).strip()}


def topic_match_score(tag_names: set[str], seed: dict) -> tuple[int, int]:
    primary_hits = tag_names.intersection(_primary_tags(seed))
    support_hits = tag_names.intersection(_support_tags(seed))
    score = len(primary_hits) * 3 + len(support_hits - primary_hits)
    return score, len(primary_hits)


def cluster_match_score(tag_names: set[str], cluster: dict) -> tuple[int, int]:
    required_hits = tag_names.intersection(_cluster_required_tags(cluster))
    if len(required_hits) < len(_cluster_required_tags(cluster)):
        return 0, len(required_hits)
    support_hits = tag_names.intersection(_cluster_support_tags(cluster))
    score = len(required_hits) * 4 + len(support_hits - required_hits)
    return score, len(required_hits)


def _article_topic_rows(connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            a.id,
            a.title,
            a.publish_date,
            a.view_count,
            GROUP_CONCAT(t.name, ' | ') AS tag_names
        FROM articles a
        LEFT JOIN article_tags at ON at.article_id = a.id
        LEFT JOIN tags t ON t.id = at.tag_id AND t.category IN ('topic', 'industry')
        WHERE a.source = 'business'
        GROUP BY a.id
        """
    ).fetchall()
    payload: list[dict] = []
    for row in rows:
        tag_names = {
            item.strip()
            for item in (row["tag_names"] or "").split(" | ")
            if item and item.strip()
        }
        payload.append(
            {
                "id": row["id"],
                "title": row["title"],
                "publish_date": row["publish_date"] or "2000-01-01",
                "view_count": row["view_count"] or 0,
                "tag_names": tag_names,
            }
        )
    return payload


def _topic_sort_key(article: dict, match_score: int) -> tuple[int, int, str, int]:
    return (match_score, article["view_count"], article["publish_date"], article["id"])


def _clear_generated_topics(connection, topic_types: tuple[str, ...]) -> None:
    if not topic_types:
        return
    placeholders = ",".join("?" for _ in topic_types)
    topic_ids = [
        row["id"]
        for row in connection.execute(
            f"SELECT id FROM topics WHERE type IN ({placeholders})",
            topic_types,
        ).fetchall()
    ]
    if not topic_ids:
        return
    topic_placeholders = ",".join("?" for _ in topic_ids)
    connection.execute(f"DELETE FROM topic_tags WHERE topic_id IN ({topic_placeholders})", topic_ids)
    connection.execute(f"DELETE FROM topic_articles WHERE topic_id IN ({topic_placeholders})", topic_ids)
    connection.execute(f"DELETE FROM topics WHERE id IN ({topic_placeholders})", topic_ids)


def _build_tag_lookup(connection) -> dict[str, list[int]]:
    tag_rows = connection.execute("SELECT id, name FROM tags").fetchall()
    tag_name_to_ids: dict[str, list[int]] = defaultdict(list)
    for row in tag_rows:
        tag_name_to_ids[row["name"]].append(row["id"])
    return tag_name_to_ids


def _insert_topic(
    connection,
    *,
    now: str,
    title: str,
    slug: str,
    description: str,
    topic_type: str,
    auto_rules: dict,
    matched_rows: list[dict],
    tag_names: set[str],
    editor_note: str,
) -> dict:
    cover_article_id = matched_rows[0]["id"]
    head_views = [item["view_count"] for item in matched_rows[:5]]
    view_count = int(sum(head_views) / max(len(head_views), 1))

    connection.execute(
        """
        INSERT INTO topics (
            title, slug, description, cover_image, cover_article_id, type, auto_rules,
            status, created_at, updated_at, view_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'published', ?, ?, ?)
        """,
        (
            title,
            slug,
            description,
            None,
            cover_article_id,
            topic_type,
            json.dumps(auto_rules, ensure_ascii=False),
            now,
            now,
            view_count,
        ),
    )
    topic_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]

    for sort_order, article in enumerate(matched_rows, start=1):
        connection.execute(
            """
            INSERT INTO topic_articles (topic_id, article_id, sort_order, editor_note)
            VALUES (?, ?, ?, ?)
            """,
            (topic_id, article["id"], sort_order, editor_note),
        )

    tag_lookup = _build_tag_lookup(connection)
    for tag_name in sorted(tag_names):
        for tag_id in tag_lookup.get(tag_name, []):
            connection.execute(
                """
                INSERT OR IGNORE INTO topic_tags (topic_id, tag_id)
                VALUES (?, ?)
                """,
                (topic_id, tag_id),
            )

    return {
        "id": topic_id,
        "title": title,
        "slug": slug,
        "article_count": len(matched_rows),
    }


def _insert_seed_topics(connection, now: str) -> list[dict]:
    article_rows = _article_topic_rows(connection)
    created_topics: list[dict] = []
    for seed in TOPIC_SEEDS:
        matched_rows: list[dict] = []
        for article in article_rows:
            match_score, primary_hit_count = topic_match_score(article["tag_names"], seed)
            if primary_hit_count < 1 or match_score < 3:
                continue
            matched_rows.append({**article, "match_score": match_score})

        if len(matched_rows) < 6:
            continue

        matched_rows.sort(key=lambda item: _topic_sort_key(item, item["match_score"]), reverse=True)
        matched_rows = matched_rows[:24]
        years = sorted(item["publish_date"][:4] for item in matched_rows if item["publish_date"])
        description = (
            f"{seed['description_prefix']} 本专题当前聚合 {len(matched_rows)} 篇业务文章，"
            f"覆盖 {years[0]} 到 {years[-1]}，可用于快速把握主题脉络与代表案例。"
        )
        created_topics.append(
            _insert_topic(
                connection,
                now=now,
                title=seed["title"],
                slug=seed["slug"],
                description=description,
                topic_type="seed",
                auto_rules={
                    "primary_tags": sorted(_primary_tags(seed)),
                    "support_tags": sorted(_support_tags(seed)),
                },
                matched_rows=matched_rows,
                tag_names=_all_seed_tags(seed),
                editor_note=f"围绕 {seed['title']} 生成的主线专题",
            )
        )
    return created_topics


def _insert_cluster_topics(connection, now: str, limit: int = 8) -> list[dict]:
    safe_limit = max(0, min(limit, len(TOPIC_AUTO_CLUSTERS)))
    if safe_limit == 0:
        return []

    article_rows = _article_topic_rows(connection)
    created_topics: list[dict] = []
    for cluster in TOPIC_AUTO_CLUSTERS[:safe_limit]:
        required_tags = _cluster_required_tags(cluster)
        support_tags = _cluster_support_tags(cluster)
        matched_rows: list[dict] = []
        for article in article_rows:
            match_score, required_hits = cluster_match_score(article["tag_names"], cluster)
            if required_hits < len(required_tags) or match_score < len(required_tags) * 4:
                continue
            matched_rows.append({**article, "match_score": match_score})

        min_articles = int(cluster.get("min_articles") or 8)
        if len(matched_rows) < min_articles:
            continue

        matched_rows.sort(key=lambda item: _topic_sort_key(item, item["match_score"]), reverse=True)
        article_limit = max(8, min(int(cluster.get("article_limit") or 18), 24))
        matched_rows = matched_rows[:article_limit]
        years = sorted(item["publish_date"][:4] for item in matched_rows if item["publish_date"])
        description = (
            f"{cluster['description_prefix']} 本专题当前聚合 {len(matched_rows)} 篇业务文章，"
            f"覆盖 {years[0]} 到 {years[-1]}，适合按专题理解代表案例与演进脉络。"
        )
        created_topics.append(
            _insert_topic(
                connection,
                now=now,
                title=cluster["title"],
                slug=_unique_topic_slug(connection, cluster["slug"]),
                description=description,
                topic_type="auto",
                auto_rules={
                    "required_tags": sorted(required_tags),
                    "support_tags": sorted(support_tags),
                },
                matched_rows=matched_rows,
                tag_names=required_tags | support_tags,
                editor_note=f"围绕 {cluster['title']} 自动聚合的高信号专题",
            )
        )
    return created_topics


def rebuild_topics(
    *,
    connection: sqlite3.Connection | None = None,
    limit_auto: int = 8,
) -> dict:
    if connection is None:
        with connection_scope() as managed_connection:
            result = rebuild_topics(connection=managed_connection, limit_auto=limit_auto)
            managed_connection.commit()
            return result

    now = datetime.utcnow().isoformat()
    _clear_generated_topics(connection, ("seed", "auto"))
    seed_topics = _insert_seed_topics(connection, now)
    auto_topics = _insert_cluster_topics(connection, now, limit=limit_auto)
    return {
        "created_count": len(seed_topics) + len(auto_topics),
        "seed_topics": seed_topics,
        "auto_topics": auto_topics,
    }


def auto_generate_topics(limit: int = 8) -> dict:
    safe_limit = max(1, min(limit, len(TOPIC_AUTO_CLUSTERS)))
    now = datetime.utcnow().isoformat()
    with connection_scope() as connection:
        _clear_generated_topics(connection, ("auto",))
        created_topics = _insert_cluster_topics(connection, now, limit=safe_limit)
        connection.commit()
    return {
        "created_count": len(created_topics),
        "topics": created_topics,
    }
