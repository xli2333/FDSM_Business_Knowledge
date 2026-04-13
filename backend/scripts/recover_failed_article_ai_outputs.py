from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import SQLITE_DB_PATH
from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.scripts.article_ai_batch import LOG_DIR, load_api_keys, now_iso, process_article


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover failed article_ai_outputs rows.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of failed articles to retry.")
    parser.add_argument("--worker-name", type=str, default="recovery_live", help="Worker name recorded in the database.")
    return parser.parse_args()


def list_failed_article_ids(limit: int = 0) -> list[int]:
    query = """
        SELECT article_id
        FROM article_ai_outputs
        WHERE status = 'failed'
           OR summary_status = 'failed'
           OR format_status = 'failed'
           OR translation_status = 'failed'
        ORDER BY article_id DESC
    """
    params: tuple[object, ...] = ()
    if limit > 0:
        query += " LIMIT ?"
        params = (limit,)
    with connection_scope() as connection:
        rows = connection.execute(query, params).fetchall()
    return [int(row["article_id"]) for row in rows]


def get_failed_total() -> int:
    with connection_scope() as connection:
        return int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM article_ai_outputs
                WHERE status = 'failed'
                   OR summary_status = 'failed'
                   OR format_status = 'failed'
                   OR translation_status = 'failed'
                """
            ).fetchone()[0]
        )


def mark_interrupted(article_id: int, worker_name: str) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE article_ai_outputs
            SET status = CASE WHEN status = 'running' THEN 'failed' ELSE status END,
                summary_status = CASE WHEN summary_status = 'running' THEN 'failed' ELSE summary_status END,
                format_status = CASE WHEN format_status = 'running' THEN 'failed' ELSE format_status END,
                translation_status = CASE WHEN translation_status = 'running' THEN 'failed' ELSE translation_status END,
                summary_error = CASE
                    WHEN summary_status = 'running' AND COALESCE(summary_error, '') = ''
                    THEN 'Recovery run interrupted by user.'
                    ELSE summary_error
                END,
                format_error = CASE
                    WHEN format_status = 'running' AND COALESCE(format_error, '') = ''
                    THEN 'Recovery run interrupted by user.'
                    ELSE format_error
                END,
                translation_error = CASE
                    WHEN translation_status = 'running' AND COALESCE(translation_error, '') = ''
                    THEN 'Recovery run interrupted by user.'
                    ELSE translation_error
                END,
                error_message = 'Recovery run interrupted by user.',
                worker_name = ?,
                updated_at = ?
            WHERE article_id = ?
              AND (
                    status = 'running'
                 OR summary_status = 'running'
                 OR format_status = 'running'
                 OR translation_status = 'running'
              )
            """,
            (worker_name, now_iso(), article_id),
        )
        connection.commit()


def build_logger(worker_name: str) -> logging.Logger:
    logger = logging.getLogger(f"recover-failed.{worker_name}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_DIR / f"{worker_name}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def print_banner(args: argparse.Namespace, failed_ids: list[int]) -> None:
    print("=" * 72)
    print("FDSM article_ai_outputs recovery")
    print(f"database: {SQLITE_DB_PATH}")
    print(f"worker : {args.worker_name}")
    print(f"queued : {len(failed_ids)}")
    print(f"limit  : {args.limit or 'all'}")
    print("=" * 72)


def main() -> int:
    args = parse_args()
    ensure_database_ready()
    ensure_runtime_tables()

    failed_ids = list_failed_article_ids(args.limit)
    print_banner(args, failed_ids)
    if not failed_ids:
        print("No failed article_ai_outputs rows remain.")
        return 0

    api_keys = load_api_keys()
    logger = build_logger(args.worker_name)
    completed = 0
    failed = 0
    current_article_id: int | None = None

    try:
        for index, article_id in enumerate(failed_ids, start=1):
            current_article_id = article_id
            logger.info("[%s/%s] recovering article %s", index, len(failed_ids), article_id)
            try:
                result = process_article(
                    article_id,
                    worker_name=args.worker_name,
                    api_keys=api_keys,
                    sequence_index=index,
                    logger=logger,
                )
                completed += 1
                logger.info(
                    "[%s/%s] article %s %s | remaining_failed=%s",
                    index,
                    len(failed_ids),
                    article_id,
                    result,
                    get_failed_total(),
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.exception("[%s/%s] article %s failed: %s", index, len(failed_ids), article_id, exc)
            finally:
                current_article_id = None
    except KeyboardInterrupt:
        logger.warning("Recovery interrupted by user.")
        if current_article_id is not None:
            mark_interrupted(current_article_id, args.worker_name)
        raise

    remaining = get_failed_total()
    print("-" * 72)
    print(f"completed_this_run: {completed}")
    print(f"failed_this_run   : {failed}")
    print(f"remaining_failed  : {remaining}")
    print("-" * 72)
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
