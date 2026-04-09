from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.scripts.article_ai_batch import upsert_output_snapshot
from backend.services.article_ai_output_service import build_current_article_source_hash, fetch_latest_article_ai_output_row
from backend.services.fudan_wechat_renderer import (
    FudanWechatRenderError,
    build_fudan_render_item,
    render_fudan_wechat,
    render_fudan_wechat_batch,
)
from backend.services.summary_preview_service import render_summary_preview_html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-render selected articles with the Fudan WeChat template.")
    parser.add_argument("--ids", nargs="+", type=int, required=True)
    parser.add_argument("--worker-name", type=str, default="rerender-selected-articles")
    parser.add_argument("--chunk-size", type=int, default=4)
    return parser.parse_args()


def render_jobs_with_fallback(jobs: list[dict]) -> list[dict]:
    if not jobs:
        return []
    try:
        return render_fudan_wechat_batch(jobs, timeout_seconds=max(180.0, len(jobs) * 16.0))
    except FudanWechatRenderError:
        return [render_fudan_wechat(job, timeout_seconds=90.0) for job in jobs]


def main() -> int:
    args = parse_args()
    article_ids = [article_id for article_id in args.ids if article_id > 0]
    if not article_ids:
        raise SystemExit("No valid article ids provided.")

    ensure_database_ready()
    ensure_runtime_tables()

    with connection_scope() as connection:
        rows = connection.execute(
            f"SELECT * FROM articles WHERE id IN ({','.join('?' for _ in article_ids)}) ORDER BY publish_date DESC, id DESC",
            article_ids,
        ).fetchall()
        article_map = {row["id"]: dict(row) for row in rows}

        jobs: list[dict] = []
        descriptors: list[dict] = []

        for article_id in article_ids:
            article = article_map.get(article_id)
            if article is None:
                continue
            source_hash = build_current_article_source_hash(article)
            ai_row = fetch_latest_article_ai_output_row(connection, article_id, source_hash=source_hash)
            if ai_row is None:
                ai_row = fetch_latest_article_ai_output_row(connection, article_id)
            if ai_row is None:
                continue

            ai_payload = dict(ai_row)
            zh_content = str(ai_payload.get("formatted_markdown_zh") or article.get("content") or "").strip()
            zh_summary = str(ai_payload.get("summary_zh") or article.get("excerpt") or article.get("main_topic") or "").strip()

            descriptor = {
                "article": article,
                "ai_row": ai_payload,
                "source_hash": source_hash,
                "zh_index": len(jobs),
            }
            jobs.append(
                build_fudan_render_item(
                    title=article.get("title") or "",
                    content_markdown=zh_content,
                    summary=zh_summary,
                    source_url=article.get("link"),
                )
            )

            en_content = str(ai_payload.get("formatted_markdown_en") or ai_payload.get("translation_content_en") or "").strip()
            if en_content:
                descriptor["en_index"] = len(jobs)
                jobs.append(
                    build_fudan_render_item(
                        title=str(ai_payload.get("translation_title_en") or article.get("title") or "").strip(),
                        content_markdown=en_content,
                        summary=str(ai_payload.get("translation_summary_en") or "").strip(),
                        source_url=article.get("link"),
                    )
                )
            descriptors.append(descriptor)

        if not jobs:
            print({"article_count": 0, "job_count": 0})
            return 0

        chunk_size = max(1, args.chunk_size)
        for offset in range(0, len(descriptors), chunk_size):
            descriptor_chunk = descriptors[offset : offset + chunk_size]
            index_map: dict[int, int] = {}
            chunk_jobs: list[dict] = []
            for local_index, descriptor in enumerate(descriptor_chunk):
                index_map[descriptor["zh_index"]] = len(chunk_jobs)
                chunk_jobs.append(jobs[descriptor["zh_index"]])
                if "en_index" in descriptor:
                    index_map[descriptor["en_index"]] = len(chunk_jobs)
                    chunk_jobs.append(jobs[descriptor["en_index"]])

            results = render_jobs_with_fallback(chunk_jobs)

            for descriptor in descriptor_chunk:
                article = descriptor["article"]
                ai_payload = descriptor["ai_row"]
                zh_result = results[index_map[descriptor["zh_index"]]]
                updates = {
                    "summary_zh": ai_payload.get("summary_zh"),
                    "summary_html_zh": render_summary_preview_html(
                        str(ai_payload.get("summary_zh") or article.get("excerpt") or article.get("main_topic") or "").strip(),
                        language="zh",
                    ),
                    "summary_model": ai_payload.get("summary_model"),
                    "formatted_markdown_zh": ai_payload.get("formatted_markdown_zh") or article.get("content") or "",
                    "formatted_markdown_en": ai_payload.get("formatted_markdown_en"),
                    "translation_title_en": ai_payload.get("translation_title_en"),
                    "translation_excerpt_en": ai_payload.get("translation_excerpt_en"),
                    "translation_summary_en": ai_payload.get("translation_summary_en"),
                    "summary_html_en": render_summary_preview_html(
                        str(ai_payload.get("translation_summary_en") or "").strip(),
                        language="en",
                    ),
                    "translation_content_en": ai_payload.get("translation_content_en"),
                    "html_web_zh": zh_result.get("previewHtml") or zh_result.get("contentHtml") or "",
                    "html_wechat_zh": zh_result.get("previewHtml") or zh_result.get("contentHtml") or "",
                    "html_web_en": ai_payload.get("html_web_en"),
                    "html_wechat_en": ai_payload.get("html_wechat_en"),
                    "summary_status": ai_payload.get("summary_status") or "completed",
                    "format_status": ai_payload.get("format_status") or "completed",
                    "translation_status": ai_payload.get("translation_status") or ("completed" if "en_index" in descriptor else "pending"),
                    "summary_error": ai_payload.get("summary_error"),
                    "format_error": None,
                    "translation_error": ai_payload.get("translation_error"),
                    "translation_model": ai_payload.get("translation_model"),
                    "format_model": "fudan-wechat-preview-bridge-beauty",
                }
                if "en_index" in descriptor:
                    en_result = results[index_map[descriptor["en_index"]]]
                    updates["html_web_en"] = en_result.get("previewHtml") or en_result.get("contentHtml") or ""
                    updates["html_wechat_en"] = en_result.get("previewHtml") or en_result.get("contentHtml") or ""

                upsert_output_snapshot(
                    connection,
                    article=article,
                    source_hash=descriptor["source_hash"],
                    worker_name=args.worker_name,
                    started_at=ai_payload.get("updated_at") or ai_payload.get("created_at") or "",
                    updates=updates,
                )

        connection.commit()

    print({"article_count": len(descriptors), "job_count": len(jobs)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
