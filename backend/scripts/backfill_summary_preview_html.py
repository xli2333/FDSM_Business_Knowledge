from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.scripts.article_ai_batch import run_write_transaction, upsert_output_snapshot
from backend.services.article_ai_output_service import build_current_article_source_hash, fetch_latest_article_ai_output_row
from backend.services.article_visibility_service import is_hidden_low_value_article
from backend.services.summary_preview_service import render_summary_preview_html


DEFAULT_CHUNK_SIZE = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill persisted summary preview HTML assets.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--worker-name", type=str, default="summary-preview-backfill")
    return parser.parse_args()


def fetch_candidates(limit: int) -> list[dict[str, Any]]:
    safe_limit = max(limit, 0)
    with connection_scope() as connection:
        query = """
            SELECT
                id,
                doc_id,
                slug,
                relative_path,
                title,
                excerpt,
                main_topic,
                content,
                publish_date,
                source,
                link,
                access_level
            FROM articles
            WHERE source != 'editorial'
            ORDER BY publish_date DESC, id DESC
        """
        params: tuple[Any, ...] = ()
        if safe_limit:
            query += " LIMIT ?"
            params = (safe_limit,)
        rows = connection.execute(query, params).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            article = dict(row)
            if is_hidden_low_value_article(article):
                continue
            source_hash = build_current_article_source_hash(article)
            ai_row = fetch_latest_article_ai_output_row(connection, article["id"], source_hash=source_hash)
            if ai_row is None:
                ai_row = fetch_latest_article_ai_output_row(connection, article["id"])
            if ai_row is None:
                continue
            candidates.append(
                {
                    "article": article,
                    "source_hash": source_hash,
                    "ai_row": dict(ai_row),
                }
            )
        return candidates


def main() -> int:
    args = parse_args()
    ensure_database_ready()
    ensure_runtime_tables()

    candidates = fetch_candidates(args.limit)
    chunk_size = max(1, args.chunk_size)
    processed = 0

    for offset in range(0, len(candidates), chunk_size):
        chunk = candidates[offset : offset + chunk_size]

        def write(connection) -> None:
            nonlocal processed
            for item in chunk:
                article = item["article"]
                ai_row = item["ai_row"]
                summary_zh = str(ai_row.get("summary_zh") or article.get("excerpt") or article.get("main_topic") or "").strip()
                summary_en = str(ai_row.get("translation_summary_en") or "").strip()
                upsert_output_snapshot(
                    connection,
                    article=article,
                    source_hash=item["source_hash"],
                    worker_name=args.worker_name,
                    started_at=ai_row.get("started_at") or ai_row.get("created_at") or ai_row.get("updated_at") or "",
                    updates={
                        "summary_html_zh": render_summary_preview_html(summary_zh, language="zh"),
                        "summary_html_en": render_summary_preview_html(summary_en, language="en"),
                    },
                )
                processed += 1

        run_write_transaction(write)

    print({"processed": processed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
