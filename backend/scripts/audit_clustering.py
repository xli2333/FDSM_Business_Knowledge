from __future__ import annotations

import json
import sqlite3
import sys
from itertools import combinations
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import SQLITE_DB_PATH


def build_report(connection: sqlite3.Connection) -> dict:
    connection.row_factory = sqlite3.Row

    topic_rows = connection.execute(
        """
        SELECT id, slug, title, type
        FROM topics
        WHERE status = 'published'
        ORDER BY title ASC
        """
    ).fetchall()
    topic_ids = [row["id"] for row in topic_rows]

    column_counts = [
        dict(row)
        for row in connection.execute(
            """
            SELECT c.slug, c.name, COUNT(ac.article_id) AS article_count
            FROM columns c
            LEFT JOIN article_columns ac ON ac.column_id = c.id
            GROUP BY c.id
            ORDER BY c.sort_order ASC
            """
        ).fetchall()
    ]

    topic_counts = [
        dict(row)
        for row in connection.execute(
            """
            SELECT type, COUNT(*) AS count
            FROM topics
            GROUP BY type
            ORDER BY count DESC, type ASC
            """
        ).fetchall()
    ]

    topic_article_counts = [
        dict(row)
        for row in connection.execute(
            """
            SELECT t.slug, t.title, t.type, COUNT(ta.article_id) AS article_count
            FROM topics t
            LEFT JOIN topic_articles ta ON ta.topic_id = t.id
            GROUP BY t.id
            ORDER BY article_count DESC, t.title ASC
            """
        ).fetchall()
    ]

    avg_columns = connection.execute(
        """
        SELECT ROUND(AVG(c), 2)
        FROM (
            SELECT COUNT(*) AS c
            FROM article_columns
            GROUP BY article_id
        )
        """
    ).fetchone()[0]

    multi_column = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT article_id
            FROM article_columns
            GROUP BY article_id
            HAVING COUNT(*) >= 2
        )
        """
    ).fetchone()[0]

    triple_column = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT article_id
            FROM article_columns
            GROUP BY article_id
            HAVING COUNT(*) >= 3
        )
        """
    ).fetchone()[0]

    industry_total = connection.execute(
        """
        SELECT COUNT(*)
        FROM article_columns ac
        JOIN columns c ON c.id = ac.column_id
        WHERE c.slug = 'industry'
        """
    ).fetchone()[0]

    industry_without_tag = connection.execute(
        """
        SELECT COUNT(*)
        FROM article_columns ac
        JOIN columns c ON c.id = ac.column_id
        LEFT JOIN (
            SELECT at.article_id, SUM(CASE WHEN t.category = 'industry' THEN 1 ELSE 0 END) AS industry_tag_count
            FROM article_tags at
            JOIN tags t ON t.id = at.tag_id
            GROUP BY at.article_id
        ) tag_stats ON tag_stats.article_id = ac.article_id
        WHERE c.slug = 'industry'
          AND COALESCE(tag_stats.industry_tag_count, 0) = 0
        """
    ).fetchone()[0]

    overlap_pairs: list[dict] = []
    topic_slug_lookup = {row["id"]: row["slug"] for row in topic_rows}
    for topic_a, topic_b in combinations(topic_ids, 2):
        overlap = connection.execute(
            """
            SELECT COUNT(*)
            FROM topic_articles ta1
            JOIN topic_articles ta2 ON ta1.article_id = ta2.article_id
            WHERE ta1.topic_id = ? AND ta2.topic_id = ?
            """,
            (topic_a, topic_b),
        ).fetchone()[0]
        if overlap:
            overlap_pairs.append(
                {
                    "topic_a": topic_slug_lookup[topic_a],
                    "topic_b": topic_slug_lookup[topic_b],
                    "overlap": overlap,
                }
            )

    overlap_pairs.sort(key=lambda item: (-item["overlap"], item["topic_a"], item["topic_b"]))

    return {
        "topic_count": len(topic_rows),
        "topic_type_counts": topic_counts,
        "topic_article_counts": topic_article_counts,
        "column_counts": column_counts,
        "avg_columns_per_article": avg_columns,
        "articles_with_2plus_columns": multi_column,
        "articles_with_3plus_columns": triple_column,
        "industry_column_total": industry_total,
        "industry_column_without_industry_tags": industry_without_tag,
        "industry_column_without_industry_tags_ratio": round(
            industry_without_tag / industry_total, 4
        )
        if industry_total
        else 0.0,
        "top_topic_overlaps": overlap_pairs[:10],
    }


def strict_failures(report: dict) -> list[str]:
    failures: list[str] = []
    if report["topic_count"] < 12:
        failures.append("topic_count < 12")
    if report["industry_column_without_industry_tags_ratio"] > 0.25:
        failures.append("industry leakage ratio > 0.25")
    if (report["avg_columns_per_article"] or 0) > 1.8:
        failures.append("avg columns per article > 1.8")
    return failures


def main() -> None:
    strict = "--strict" in sys.argv[1:]
    connection = sqlite3.connect(SQLITE_DB_PATH)
    try:
        report = build_report(connection)
    finally:
        connection.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if strict:
        failures = strict_failures(report)
        if failures:
            raise SystemExit("CLUSTER_AUDIT_FAILED: " + "; ".join(failures))


if __name__ == "__main__":
    main()
