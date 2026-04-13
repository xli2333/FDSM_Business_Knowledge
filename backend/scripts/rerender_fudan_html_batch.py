from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.scripts.article_ai_batch import make_logger, run_write_transaction, upsert_output_snapshot
from backend.services.article_ai_output_service import build_current_article_source_hash, fetch_latest_article_ai_output_row
from backend.services.article_visibility_service import is_hidden_low_value_article
from backend.services.fudan_wechat_renderer import (
    FudanWechatRenderError,
    build_fudan_render_item,
    render_fudan_wechat,
    render_fudan_wechat_batch,
)
from backend.services.summary_preview_service import render_summary_preview_html


DEFAULT_CHUNK_SIZE = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-render existing article HTML with the real Fudan WeChat template.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--total-shards", type=int, default=1)
    parser.add_argument("--worker-name", type=str, default="fudan-html-rerender")
    return parser.parse_args()


def fetch_candidate_rows(limit: int, shard_index: int, total_shards: int) -> list[dict[str, Any]]:
    safe_limit = max(limit, 0)
    with connection_scope() as connection:
        query = """
            SELECT
                id,
                doc_id,
                slug,
                relative_path,
                title,
                publish_date,
                source,
                excerpt,
                main_topic,
                article_type,
                primary_org_name,
                access_level,
                link,
                content
            FROM articles
            WHERE source != 'editorial'
            ORDER BY publish_date DESC, id DESC
        """
        params: tuple[Any, ...] = ()
        if safe_limit:
            query += " LIMIT ?"
            params = (safe_limit,)
        rows = connection.execute(query, params).fetchall()

    visible_rows = [dict(row) for row in rows if not is_hidden_low_value_article(row)]
    return [row for index, row in enumerate(visible_rows) if index % max(total_shards, 1) == max(shard_index, 0)]


def fetch_latest_translation_row(connection, article_id: int, source_hash: str):
    row = connection.execute(
        """
        SELECT title, excerpt, summary, content, updated_at
        FROM article_translations
        WHERE article_id = ? AND target_lang = 'en' AND source_hash = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (article_id, source_hash),
    ).fetchone()
    if row is not None:
        return row
    return connection.execute(
        """
        SELECT title, excerpt, summary, content, updated_at
        FROM article_translations
        WHERE article_id = ? AND target_lang = 'en'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()


def build_english_assets(article_row, ai_row, translation_row) -> dict[str, str]:
    return {
        "title": str(
            (ai_row["translation_title_en"] if ai_row else "")
            or (translation_row["title"] if translation_row else "")
            or article_row["title"]
            or ""
        ).strip(),
        "summary": str(
            (ai_row["translation_summary_en"] if ai_row else "")
            or (translation_row["summary"] if translation_row else "")
            or ""
        ).strip(),
        "content": str(
            (ai_row["formatted_markdown_en"] if ai_row else "")
            or (ai_row["translation_content_en"] if ai_row else "")
            or (translation_row["content"] if translation_row else "")
            or ""
        ).strip(),
    }


def build_render_jobs(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs: list[dict[str, Any]] = []
    descriptors: list[dict[str, Any]] = []

    with connection_scope() as connection:
        for row in rows:
            article_id = row["id"]
            source_hash = build_current_article_source_hash(row)
            ai_row = fetch_latest_article_ai_output_row(connection, article_id, source_hash=source_hash)
            if ai_row is None:
                ai_row = fetch_latest_article_ai_output_row(connection, article_id)
            translation_row = fetch_latest_translation_row(connection, article_id, source_hash)

            zh_content = str((ai_row["formatted_markdown_zh"] if ai_row else "") or row.get("content") or "").strip()
            zh_summary = str(
                (ai_row["summary_zh"] if ai_row else "") or row.get("excerpt") or row.get("main_topic") or ""
            ).strip()
            en_assets = build_english_assets(row, ai_row, translation_row)

            descriptors.append(
                {
                    "article": row,
                    "source_hash": source_hash,
                    "ai_row": dict(ai_row) if ai_row is not None else None,
                    "zh_index": len(jobs),
                    "has_en": bool(en_assets["content"]),
                }
            )
            jobs.append(
                build_fudan_render_item(
                    title=row["title"],
                    content_markdown=zh_content,
                    summary=zh_summary,
                    source_url=row.get("link"),
                )
            )

            if en_assets["content"]:
                descriptors[-1]["en_index"] = len(jobs)
                jobs.append(
                    build_fudan_render_item(
                        title=en_assets["title"] or row["title"],
                        content_markdown=en_assets["content"],
                        summary=en_assets["summary"],
                        source_url=row.get("link"),
                    )
                )

    return jobs, descriptors


def render_jobs_with_fallback(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not jobs:
        return []
    try:
        return render_fudan_wechat_batch(jobs, timeout_seconds=max(120.0, len(jobs) * 12.0))
    except FudanWechatRenderError:
        results = []
        for job in jobs:
            results.append(render_fudan_wechat(job, timeout_seconds=60.0))
        return results


def persist_render_results(descriptors: list[dict[str, Any]], results: list[dict[str, Any]], worker_name: str) -> tuple[int, int]:
    success_count = 0
    english_count = 0

    def write(connection):
        nonlocal success_count, english_count
        for descriptor in descriptors:
            article = descriptor["article"]
            source_hash = descriptor["source_hash"]
            ai_row = descriptor["ai_row"] or {}
            zh_result = results[descriptor["zh_index"]]
            updates = {
                "summary_zh": ai_row.get("summary_zh"),
                "summary_html_zh": render_summary_preview_html(
                    str(ai_row.get("summary_zh") or article.get("excerpt") or article.get("main_topic") or "").strip(),
                    language="zh",
                ),
                "summary_model": ai_row.get("summary_model"),
                "formatted_markdown_zh": ai_row.get("formatted_markdown_zh") or article.get("content") or "",
                "formatted_markdown_en": ai_row.get("formatted_markdown_en"),
                "translation_title_en": ai_row.get("translation_title_en"),
                "translation_excerpt_en": ai_row.get("translation_excerpt_en"),
                "translation_summary_en": ai_row.get("translation_summary_en"),
                "summary_html_en": render_summary_preview_html(
                    str(ai_row.get("translation_summary_en") or "").strip(),
                    language="en",
                ),
                "translation_content_en": ai_row.get("translation_content_en"),
                "html_web_zh": zh_result.get("previewHtml") or zh_result.get("contentHtml") or "",
                "html_wechat_zh": zh_result.get("previewHtml") or zh_result.get("contentHtml") or "",
                "html_web_en": ai_row.get("html_web_en"),
                "html_wechat_en": ai_row.get("html_wechat_en"),
                "summary_status": ai_row.get("summary_status") or "completed",
                "format_status": ai_row.get("format_status") or "completed",
                "translation_status": ai_row.get("translation_status") or ("completed" if descriptor.get("has_en") else "pending"),
                "summary_error": ai_row.get("summary_error"),
                "format_error": None,
                "translation_error": ai_row.get("translation_error"),
                "translation_model": ai_row.get("translation_model"),
                "format_model": ai_row.get("format_model") or "fudan-wechat-preview-bridge",
            }
            if descriptor.get("has_en"):
                en_result = results[descriptor["en_index"]]
                updates["html_web_en"] = en_result.get("previewHtml") or en_result.get("contentHtml") or ""
                updates["html_wechat_en"] = en_result.get("previewHtml") or en_result.get("contentHtml") or ""
                english_count += 1
            upsert_output_snapshot(
                connection,
                article=article,
                source_hash=source_hash,
                worker_name=worker_name,
                started_at=ai_row.get("started_at") or ai_row.get("created_at") or ai_row.get("updated_at") or "",
                updates=updates,
            )
            success_count += 1

    run_write_transaction(write)
    return success_count, english_count


def main() -> int:
    args = parse_args()
    ensure_database_ready()
    ensure_runtime_tables()

    rows = fetch_candidate_rows(args.limit, args.shard_index, args.total_shards)
    logger = make_logger(args.worker_name)
    logger.info("loaded %s visible articles for shard %s/%s", len(rows), args.shard_index, args.total_shards)

    chunk_size = max(1, args.chunk_size)
    processed = 0
    english_processed = 0
    failures: list[dict[str, Any]] = []

    for offset in range(0, len(rows), chunk_size):
        chunk_rows = rows[offset : offset + chunk_size]
        try:
            jobs, descriptors = build_render_jobs(chunk_rows)
            results = render_jobs_with_fallback(jobs)
            chunk_processed, chunk_english = persist_render_results(descriptors, results, args.worker_name)
            processed += chunk_processed
            english_processed += chunk_english
            logger.info(
                "processed chunk %s-%s | zh=%s en=%s",
                offset + 1,
                offset + len(chunk_rows),
                chunk_processed,
                chunk_english,
            )
        except Exception as exc:  # noqa: BLE001
            failure = {
                "offset": offset,
                "ids": [row["id"] for row in chunk_rows],
                "error": str(exc),
            }
            failures.append(failure)
            logger.exception("chunk failed: %s", json.dumps(failure, ensure_ascii=False))

    payload = {
        "worker_name": args.worker_name,
        "shard_index": args.shard_index,
        "total_shards": args.total_shards,
        "article_count": len(rows),
        "processed": processed,
        "english_processed": english_processed,
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
