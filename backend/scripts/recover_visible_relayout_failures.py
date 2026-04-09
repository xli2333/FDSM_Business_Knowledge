from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.scripts.article_ai_batch import make_logger, run_write_transaction, upsert_output_snapshot
from backend.scripts.article_relayout_batch import (
    build_manifest,
    derive_english_summary_fallback,
    derive_summary_fallback,
    english_assets_from_rows,
    fetch_existing_output_row,
    fetch_existing_translation_row,
    fetch_article,
    fetch_article_tags,
    render_variants,
)
from backend.services.article_asset_service import build_article_source_hash, now_iso, upsert_article_translation
from backend.services.article_relayout_service import RELAYOUT_MODEL, RELAYOUT_TEMPLATE, clean_model_fence, cleanup_source_tail, normalize_markdown_output
from backend.services.article_visibility_service import is_hidden_low_value_article


def _fallback_zh_content(content: str) -> str:
    cleaned = cleanup_source_tail(content, "zh")
    normalized = normalize_markdown_output(cleaned, "zh", remove_h1=True)
    return normalized or clean_model_fence(cleaned).strip()


def _fallback_en_content(content: str) -> str:
    cleaned = cleanup_source_tail(content, "en")
    normalized = normalize_markdown_output(cleaned, "en", remove_h1=True)
    return normalized or clean_model_fence(cleaned).strip()


def _recover_article(article_id: int, logger: logging.Logger) -> bool:
    with connection_scope() as connection:
        article = fetch_article(connection, article_id)
        if is_hidden_low_value_article(article):
            return False
        tags = fetch_article_tags(connection, article_id)
        source_hash = build_article_source_hash(article)
        existing_row = fetch_existing_output_row(connection, article_id, source_hash)
        translation_row = fetch_existing_translation_row(connection, article_id, source_hash)

    started_at = now_iso()
    zh_content = _fallback_zh_content(article.get("content") or "")
    zh_summary = derive_summary_fallback(
        str(existing_row["summary_zh"] if existing_row else ""),
        zh_content,
        article.get("excerpt") or article["title"],
    )

    english_source_assets = english_assets_from_rows(article, existing_row, translation_row)
    en_content = _fallback_en_content(english_source_assets["content"])
    english_assets = {
        "title": english_source_assets["title"],
        "excerpt": english_source_assets["excerpt"],
        "summary": derive_english_summary_fallback(
            english_source_assets["summary"],
            en_content,
            english_source_assets["excerpt"],
            english_source_assets["title"],
        ),
        "content": en_content,
        "model": RELAYOUT_MODEL,
    }
    rendered = render_variants(
        article,
        summary_zh=zh_summary,
        content_zh=zh_content,
        english_assets=english_assets,
        tags=tags,
    )

    def persist(connection):
        upsert_article_translation(
            connection,
            article_id=article["id"],
            language="en",
            source_hash=source_hash,
            translated=english_assets,
            timestamp=now_iso(),
        )
        return upsert_output_snapshot(
            connection,
            article=article,
            source_hash=source_hash,
            worker_name="fallback_recover",
            started_at=started_at,
            updates={
                "summary_zh": zh_summary,
                "summary_model": RELAYOUT_MODEL,
                "formatted_markdown_zh": zh_content,
                "formatted_markdown_en": english_assets["content"],
                "translation_title_en": english_assets["title"],
                "translation_excerpt_en": english_assets["excerpt"],
                "translation_summary_en": english_assets["summary"],
                "translation_content_en": english_assets["content"],
                "translation_model": RELAYOUT_MODEL,
                "format_model": RELAYOUT_MODEL,
                "format_template": RELAYOUT_TEMPLATE,
                "summary_status": "completed",
                "format_status": "completed",
                "translation_status": "completed",
                "summary_error": None,
                "format_error": None,
                "translation_error": None,
                **rendered,
            },
            force_status="completed",
        )

    row = run_write_transaction(persist, logger=logger)
    logger.info("Recovered article %s with deterministic fallback.", article_id)
    return row["status"] == "completed"


def main() -> int:
    ensure_database_ready()
    ensure_runtime_tables()
    logger = make_logger("relayout.fallback_recover")

    visible_ids = {item["article_id"] for item in build_manifest(force=True)}
    with connection_scope() as connection:
        failed_rows = connection.execute(
            """
            SELECT article_id
            FROM article_ai_outputs
            WHERE format_template = ? AND status = 'failed'
            ORDER BY updated_at DESC
            """,
            (RELAYOUT_TEMPLATE,),
        ).fetchall()
    target_ids: list[int] = []
    seen_ids: set[int] = set()
    for row in failed_rows:
        article_id = int(row["article_id"])
        if article_id not in visible_ids or article_id in seen_ids:
            continue
        seen_ids.add(article_id)
        target_ids.append(article_id)
    logger.info("Visible failed relayout rows to recover: %s", len(target_ids))

    recovered = 0
    for article_id in target_ids:
        try:
            if _recover_article(article_id, logger):
                recovered += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallback recovery failed on article %s: %s", article_id, exc)

    logger.info("Fallback recovery completed: %s/%s", recovered, len(target_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
