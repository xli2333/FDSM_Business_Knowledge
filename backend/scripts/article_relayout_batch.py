from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import BUSINESS_DATA_DIR
from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.scripts.article_ai_batch import (
    BatchError,
    fetch_article,
    fetch_article_tags,
    load_api_keys,
    make_logger,
    request_gemini_text,
    run_write_transaction,
    upsert_output_snapshot,
    write_json_atomic,
)
from backend.services.article_asset_service import build_article_source_hash, now_iso, upsert_article_translation
from backend.services.article_relayout_service import (
    RELAYOUT_MODEL,
    RELAYOUT_TEMPLATE,
    build_en_relayout_prompt,
    build_zh_relayout_prompt,
    clean_model_fence,
    cleanup_source_tail,
    normalize_markdown_output,
    parse_json_payload,
    relayout_is_close_enough,
    summary_needs_regeneration,
)
from backend.services.display_markdown_service import (
    normalize_article_display_markdown,
    normalize_summary_display_markdown,
)
from backend.services.fudan_wechat_renderer import build_fudan_render_item, render_fudan_wechat_batch
from backend.services.html_renderer import strip_markdown
from backend.services.article_visibility_service import is_hidden_low_value_article

BATCH_ROOT = BUSINESS_DATA_DIR / "article_relayout_batch"
LOG_DIR = BATCH_ROOT / "logs"
STATE_DIR = BATCH_ROOT / "state"
MANIFEST_PATH = BATCH_ROOT / "manifest.json"
RUN_META_PATH = BATCH_ROOT / "run_meta.json"
ORCHESTRATOR_STATE_PATH = STATE_DIR / "orchestrator.json"

DEFAULT_WORKERS = 18
DEFAULT_POLL_SECONDS = 15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relayout existing Chinese and English article assets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest", help="Build or rebuild the relayout manifest.")
    manifest_parser.add_argument("--limit", type=int, default=0)
    manifest_parser.add_argument("--rebuild", action="store_true")

    worker_parser = subparsers.add_parser("run-worker", help="Run one relayout shard.")
    worker_parser.add_argument("--shard-index", type=int, required=True)
    worker_parser.add_argument("--total-shards", type=int, required=True)
    worker_parser.add_argument("--limit", type=int, default=0)
    worker_parser.add_argument("--rebuild-manifest", action="store_true")
    worker_parser.add_argument("--worker-name", type=str, default="")

    run_all_parser = subparsers.add_parser("run-all", help="Run the full relayout batch.")
    run_all_parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    run_all_parser.add_argument("--limit", type=int, default=0)
    run_all_parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    run_all_parser.add_argument("--rebuild-manifest", action="store_true")

    subparsers.add_parser("status", help="Show current relayout batch status.")
    return parser.parse_args()


def ensure_batch_directories() -> None:
    for path in (BATCH_ROOT, LOG_DIR, STATE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def worker_state_path(worker_name: str) -> Path:
    return STATE_DIR / f"{worker_name}.json"


def worker_log_path(worker_name: str) -> Path:
    return LOG_DIR / f"{worker_name}.log"


def build_manifest(*, force: bool = False, limit: int = 0) -> list[dict[str, Any]]:
    ensure_batch_directories()
    if MANIFEST_PATH.exists() and not force and limit <= 0:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return payload["articles"]

    safe_limit = max(limit, 0)
    with connection_scope() as connection:
        query = """
            SELECT id, doc_id, slug, relative_path, title, publish_date, content
            FROM articles
            WHERE source != 'editorial'
            ORDER BY publish_date DESC, id DESC
        """
        params: tuple[Any, ...] = ()
        if safe_limit:
            query += " LIMIT ?"
            params = (safe_limit,)
        rows = connection.execute(query, params).fetchall()

    articles = [
        {
            "article_id": row["id"],
            "doc_id": row["doc_id"],
            "slug": row["slug"],
            "relative_path": row["relative_path"],
            "title": row["title"],
            "publish_date": row["publish_date"],
        }
        for row in rows
        if not is_hidden_low_value_article(row)
    ]
    payload = {
        "generated_at": now_iso(),
        "model_name": RELAYOUT_MODEL,
        "format_template": RELAYOUT_TEMPLATE,
        "article_count": len(articles),
        "articles": articles,
    }
    if safe_limit <= 0:
        write_json_atomic(MANIFEST_PATH, payload)
    return articles


def fetch_existing_output_row(connection, article_id: int, source_hash: str):
    row = connection.execute(
        """
        SELECT *
        FROM article_ai_outputs
        WHERE article_id = ? AND source_hash = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (article_id, source_hash),
    ).fetchone()
    if row is not None:
        return row
    return connection.execute(
        """
        SELECT *
        FROM article_ai_outputs
        WHERE article_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()


def fetch_existing_translation_row(connection, article_id: int, source_hash: str):
    row = connection.execute(
        """
        SELECT title, excerpt, summary, content, model, updated_at
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
        SELECT title, excerpt, summary, content, model, updated_at
        FROM article_translations
        WHERE article_id = ? AND target_lang = 'en'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()


def english_assets_from_rows(article: dict[str, Any], ai_row, translation_row) -> dict[str, str]:
    title = (
        (ai_row["translation_title_en"] if ai_row else "")
        or (translation_row["title"] if translation_row else "")
        or article["title"]
    )
    excerpt = (
        (ai_row["translation_excerpt_en"] if ai_row else "")
        or (translation_row["excerpt"] if translation_row else "")
        or article.get("main_topic")
        or article.get("excerpt")
        or ""
    )
    summary = (
        (ai_row["translation_summary_en"] if ai_row else "")
        or (translation_row["summary"] if translation_row else "")
        or ""
    )
    content = (
        (ai_row["formatted_markdown_en"] if ai_row else "")
        or (ai_row["translation_content_en"] if ai_row else "")
        or (translation_row["content"] if translation_row else "")
        or ""
    )
    return {
        "title": str(title or "").strip() or article["title"],
        "excerpt": str(excerpt or "").strip(),
        "summary": str(summary or "").strip(),
        "content": str(content or "").strip(),
    }


def derive_summary_fallback(current_summary: str, body_markdown: str, fallback_seed: str) -> str:
    normalized_summary = normalize_markdown_output(current_summary, "zh", remove_h1=True)
    if normalized_summary and not summary_needs_regeneration(normalized_summary):
        return normalized_summary
    paragraphs = [part.strip() for part in strip_markdown(body_markdown).splitlines() if part.strip()]
    if paragraphs:
        return paragraphs[0][:220].strip()
    return str(fallback_seed or "").strip()


def derive_english_summary_fallback(current_summary: str, body_markdown: str, excerpt: str, title: str) -> str:
    normalized_summary = normalize_markdown_output(current_summary, "en", remove_h1=True)
    if normalized_summary and not summary_needs_regeneration(normalized_summary):
        return normalized_summary
    paragraphs = [part.strip() for part in strip_markdown(body_markdown).splitlines() if part.strip()]
    if paragraphs:
        return paragraphs[0][:260].strip()
    return excerpt or title


def build_render_payload(
    article: dict[str, Any],
    *,
    title: str,
    excerpt: str,
    content_markdown: str,
    source_url: str | None,
    organization: str,
    author: str,
    subtitle: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "subtitle": subtitle if subtitle is not None else (article.get("main_topic") or article.get("article_type") or None),
        "author": author,
        "organization": organization,
        "publish_date": article["publish_date"],
        "source_url": source_url,
        "content_markdown": content_markdown,
        "excerpt": excerpt,
    }


def render_variants(
    article: dict[str, Any],
    *,
    summary_zh: str,
    content_zh: str,
    english_assets: dict[str, str],
    tags: list[dict[str, Any]],
) -> dict[str, str]:
    source_url = article.get("link") or None
    rendered: dict[str, str] = {}
    render_jobs = [
        build_fudan_render_item(
            title=article["title"],
            content_markdown=content_zh,
            summary=summary_zh or article.get("excerpt") or article.get("main_topic") or "",
            source_url=source_url,
        )
    ]
    if str(english_assets.get("content") or "").strip():
        render_jobs.append(
            build_fudan_render_item(
                title=english_assets["title"],
                content_markdown=english_assets["content"],
                summary=english_assets.get("summary") or english_assets.get("excerpt") or "",
                source_url=source_url,
            )
        )

    render_results = render_fudan_wechat_batch(render_jobs, timeout_seconds=max(120.0, len(render_jobs) * 20.0))
    zh_rendered = render_results[0]
    rendered["html_web_zh"] = zh_rendered.get("previewHtml") or zh_rendered.get("contentHtml") or ""
    rendered["html_wechat_zh"] = zh_rendered.get("previewHtml") or zh_rendered.get("contentHtml") or ""

    if len(render_results) > 1:
        en_rendered = render_results[1]
        rendered["html_web_en"] = en_rendered.get("previewHtml") or en_rendered.get("contentHtml") or ""
        rendered["html_wechat_en"] = en_rendered.get("previewHtml") or en_rendered.get("contentHtml") or ""
    else:
        rendered["html_web_en"] = ""
        rendered["html_wechat_en"] = ""
    return rendered


def request_relayout_json(
    *,
    prompt: str,
    api_keys: list[str],
    key_offset: int,
    logger: logging.Logger,
    worker_name: str,
) -> dict[str, Any]:
    raw = request_gemini_text(
        prompt=prompt,
        api_keys=api_keys,
        key_offset=key_offset,
        logger=logger,
        worker_name=worker_name,
        response_mime_type="application/json",
        model_name=RELAYOUT_MODEL,
    )
    try:
        return parse_json_payload(raw)
    except ValueError as exc:
        raise BatchError(str(exc)) from exc


def relayout_zh_assets(
    article: dict[str, Any],
    current_summary: str,
    cleaned_source_body: str,
    *,
    api_keys: list[str],
    key_offset: int,
    logger: logging.Logger,
    worker_name: str,
) -> tuple[str, str]:
    prompt = build_zh_relayout_prompt(
        title=article["title"],
        article_type=str(article.get("article_type") or ""),
        excerpt=str(article.get("excerpt") or ""),
        main_topic=str(article.get("main_topic") or ""),
        current_summary=current_summary,
        source_body=cleaned_source_body,
        regenerate_summary=summary_needs_regeneration(current_summary),
    )
    strict_suffix = (
        "\n\nPrevious output changed the body too much. Retry and keep original sentences nearly verbatim. "
        "Only improve Markdown structure and trim unrelated tail material."
    )

    for attempt in range(2):
        payload = request_relayout_json(
            prompt=prompt if attempt == 0 else prompt + strict_suffix,
            api_keys=api_keys,
            key_offset=key_offset + attempt,
            logger=logger,
            worker_name=worker_name,
        )
        content = normalize_markdown_output(str(payload.get("content") or ""), "zh", remove_h1=True)
        summary = normalize_markdown_output(str(payload.get("summary") or ""), "zh", remove_h1=True)
        if content:
            content = normalize_article_display_markdown(content, "zh") or content
            summary = normalize_summary_display_markdown(summary, "zh") or summary
        if content and relayout_is_close_enough(cleaned_source_body, content, "zh"):
            return (
                summary or derive_summary_fallback(current_summary, content, article.get("excerpt") or article["title"]),
                content,
            )
        logger.warning("%s zh relayout drifted on article %s, retry=%s", worker_name, article["id"], attempt + 1)

    fallback_content = normalize_markdown_output(cleaned_source_body, "zh", remove_h1=True)
    structured_fallback = normalize_article_display_markdown(cleaned_source_body, "zh")
    if structured_fallback:
        fallback_content = structured_fallback
    if not fallback_content:
        fallback_content = clean_model_fence(cleaned_source_body).strip()
    fallback_summary = derive_summary_fallback(current_summary, fallback_content, article.get("excerpt") or article["title"])
    return normalize_summary_display_markdown(fallback_summary, "zh") or fallback_summary, fallback_content


def relayout_en_assets(
    english_assets: dict[str, str],
    *,
    api_keys: list[str],
    key_offset: int,
    logger: logging.Logger,
    worker_name: str,
) -> dict[str, str]:
    cleaned_content = cleanup_source_tail(english_assets["content"], "en")
    prompt = build_en_relayout_prompt(
        title=english_assets["title"],
        excerpt=english_assets["excerpt"],
        current_summary=english_assets["summary"],
        current_content=cleaned_content,
        regenerate_summary=summary_needs_regeneration(english_assets["summary"]),
    )
    strict_suffix = (
        "\n\nPrevious output changed the English body too much. Retry and keep source sentences nearly verbatim. "
        "Only improve Markdown structure and trim unrelated tail material."
    )

    for attempt in range(2):
        payload = request_relayout_json(
            prompt=prompt if attempt == 0 else prompt + strict_suffix,
            api_keys=api_keys,
            key_offset=key_offset + attempt,
            logger=logger,
            worker_name=worker_name,
        )
        content = normalize_markdown_output(str(payload.get("content") or ""), "en", remove_h1=True)
        summary = normalize_markdown_output(str(payload.get("summary") or ""), "en", remove_h1=True)
        if content:
            content = normalize_article_display_markdown(content, "en") or content
            summary = normalize_summary_display_markdown(summary, "en") or summary
        if content and relayout_is_close_enough(cleaned_content, content, "en"):
            return {
                "title": english_assets["title"],
                "excerpt": english_assets["excerpt"],
                "summary": summary
                or derive_english_summary_fallback(
                    english_assets["summary"], content, english_assets["excerpt"], english_assets["title"]
                ),
                "content": content,
                "model": RELAYOUT_MODEL,
            }
        logger.warning("%s en relayout drifted on %s, retry=%s", worker_name, english_assets["title"], attempt + 1)

    fallback_content = normalize_markdown_output(cleaned_content, "en", remove_h1=True)
    structured_fallback = normalize_article_display_markdown(cleaned_content, "en")
    if structured_fallback:
        fallback_content = structured_fallback
    if not fallback_content:
        fallback_content = clean_model_fence(cleaned_content).strip()
    fallback_summary = derive_english_summary_fallback(
        english_assets["summary"],
        fallback_content,
        english_assets["excerpt"],
        english_assets["title"],
    )
    return {
        "title": english_assets["title"],
        "excerpt": english_assets["excerpt"],
        "summary": normalize_summary_display_markdown(fallback_summary, "en") or fallback_summary,
        "content": fallback_content,
        "model": RELAYOUT_MODEL,
    }


def is_article_completed(existing_row, source_hash: str) -> bool:
    if existing_row is None:
        return False
    row = dict(existing_row)
    return (
        row.get("source_hash") == source_hash
        and row.get("summary_status") == "completed"
        and row.get("format_status") == "completed"
        and row.get("translation_status") == "completed"
        and str(row.get("summary_zh") or "").strip()
        and str(row.get("formatted_markdown_zh") or "").strip()
        and str(row.get("translation_content_en") or "").strip()
        and row.get("summary_model") == RELAYOUT_MODEL
        and row.get("format_model") == RELAYOUT_MODEL
        and row.get("translation_model") == RELAYOUT_MODEL
        and row.get("format_template") == RELAYOUT_TEMPLATE
    )


def process_article(
    article_id: int,
    *,
    worker_name: str,
    api_keys: list[str],
    sequence_index: int,
    logger: logging.Logger,
    force: bool = False,
) -> str:
    with connection_scope() as connection:
        article = fetch_article(connection, article_id)
        tags = fetch_article_tags(connection, article_id)
        source_hash = build_article_source_hash(article)
        existing_row = fetch_existing_output_row(connection, article_id, source_hash)
        translation_row = fetch_existing_translation_row(connection, article_id, source_hash)

    if not force and is_article_completed(existing_row, source_hash):
        return "skipped"

    started_at = now_iso()
    run_write_transaction(
        lambda connection: upsert_output_snapshot(
            connection,
            article=article,
            source_hash=source_hash,
            worker_name=worker_name,
            started_at=started_at,
            updates={
                "summary_status": "running",
                "format_status": "running",
                "translation_status": "running",
                "summary_error": None,
                "format_error": None,
                "translation_error": None,
                "format_template": RELAYOUT_TEMPLATE,
            },
            force_status="running",
        ),
        logger=logger,
    )

    current_summary = str(existing_row["summary_zh"] if existing_row else "").strip()
    zh_source_body = cleanup_source_tail(article.get("content") or "", "zh")
    zh_summary, zh_content = relayout_zh_assets(
        article,
        current_summary,
        zh_source_body,
        api_keys=api_keys,
        key_offset=sequence_index * 3,
        logger=logger,
        worker_name=worker_name,
    )

    english_source_assets = english_assets_from_rows(article, existing_row, translation_row)
    english_assets = relayout_en_assets(
        english_source_assets,
        api_keys=api_keys,
        key_offset=sequence_index * 3 + 1,
        logger=logger,
        worker_name=worker_name,
    )

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
            worker_name=worker_name,
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
        )

    final_row = run_write_transaction(persist, logger=logger)
    if final_row["status"] == "completed":
        return "completed"
    raise BatchError(final_row.get("error_message") or "Relayout tasks did not complete.")


def mark_article_failed(article_id: int, worker_name: str, message: str, logger: logging.Logger) -> None:
    with connection_scope() as connection:
        article = fetch_article(connection, article_id)
        source_hash = build_article_source_hash(article)
    run_write_transaction(
        lambda connection: upsert_output_snapshot(
            connection,
            article=article,
            source_hash=source_hash,
            worker_name=worker_name,
            started_at=now_iso(),
            updates={
                "summary_status": "failed",
                "format_status": "failed",
                "translation_status": "failed",
                "summary_error": message[:4000],
                "format_error": message[:4000],
                "translation_error": message[:4000],
                "format_template": RELAYOUT_TEMPLATE,
            },
            force_status="failed",
        ),
        logger=logger,
    )


def run_worker(*, shard_index: int, total_shards: int, limit: int = 0, rebuild_manifest: bool = False, worker_name: str = "") -> int:
    ensure_database_ready()
    ensure_runtime_tables()
    ensure_batch_directories()
    api_keys = load_api_keys()
    safe_worker_name = worker_name or f"worker_{shard_index + 1:02d}"
    logger = make_logger(f"relayout.{safe_worker_name}")
    manifest = build_manifest(force=rebuild_manifest, limit=limit)
    assigned = [item for idx, item in enumerate(manifest) if idx % total_shards == shard_index]
    state_path = worker_state_path(safe_worker_name)
    state = {
        "worker_name": safe_worker_name,
        "status": "running",
        "shard_index": shard_index,
        "total_shards": total_shards,
        "started_at": now_iso(),
        "assigned_count": len(assigned),
        "processed": 0,
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "current_article_id": None,
        "current_title": None,
    }
    write_json_atomic(state_path, state)
    logger.info("%s starting with %s assigned articles", safe_worker_name, len(assigned))

    for index, item in enumerate(assigned, start=1):
        article_id = item["article_id"]
        state["current_article_id"] = article_id
        state["current_title"] = item["title"]
        write_json_atomic(state_path, state)
        try:
            result = process_article(
                article_id,
                worker_name=safe_worker_name,
                api_keys=api_keys,
                sequence_index=shard_index + index,
                logger=logger,
            )
            state["processed"] += 1
            if result == "skipped":
                state["skipped"] += 1
            else:
                state["completed"] += 1
            if index % 5 == 0:
                logger.info(
                    "%s progress %s/%s | completed=%s skipped=%s failed=%s",
                    safe_worker_name,
                    index,
                    len(assigned),
                    state["completed"],
                    state["skipped"],
                    state["failed"],
                )
        except Exception as exc:  # noqa: BLE001
            state["processed"] += 1
            state["failed"] += 1
            logger.exception("%s failed on article %s: %s", safe_worker_name, article_id, exc)
            mark_article_failed(article_id, safe_worker_name, str(exc), logger)
        finally:
            write_json_atomic(state_path, state)

    state["status"] = "completed"
    state["current_article_id"] = None
    state["current_title"] = None
    state["updated_at"] = now_iso()
    write_json_atomic(state_path, state)
    logger.info(
        "%s finished | completed=%s skipped=%s failed=%s",
        safe_worker_name,
        state["completed"],
        state["skipped"],
        state["failed"],
    )
    return 0


def spawn_workers(*, worker_count: int, limit: int, rebuild_manifest: bool) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for shard_index in range(worker_count):
        worker_name = f"worker_{shard_index + 1:02d}"
        log_path = worker_log_path(worker_name)
        handle = log_path.open("a", encoding="utf-8")
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run-worker",
            "--shard-index",
            str(shard_index),
            "--total-shards",
            str(worker_count),
            "--worker-name",
            worker_name,
        ]
        if limit > 0:
            command.extend(["--limit", str(limit)])
        if rebuild_manifest:
            command.append("--rebuild-manifest")
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        processes.append(
            {
                "worker_name": worker_name,
                "pid": process.pid,
                "process": process,
                "handle": handle,
                "log_path": str(log_path),
            }
        )
    return processes


def close_handles(processes: list[dict[str, Any]]) -> None:
    for item in processes:
        handle = item.get("handle")
        if handle:
            handle.close()


def collect_db_status() -> dict[str, Any]:
    template = RELAYOUT_TEMPLATE
    with connection_scope() as connection:
        completed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND status = 'completed'
            """,
            (template,),
        ).fetchone()["total"]
        failed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND status = 'failed'
            """,
            (template,),
        ).fetchone()["total"]
        running = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND status = 'running'
            """,
            (template,),
        ).fetchone()["total"]
        summary_completed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND summary_status = 'completed'
            """
            ,
            (template,),
        ).fetchone()["total"]
        summary_failed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND summary_status = 'failed'
            """,
            (template,),
        ).fetchone()["total"]
        format_completed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND format_status = 'completed'
            """,
            (template,),
        ).fetchone()["total"]
        format_failed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND format_status = 'failed'
            """,
            (template,),
        ).fetchone()["total"]
        translation_completed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND translation_status = 'completed'
            """,
            (template,),
        ).fetchone()["total"]
        translation_failed = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ? AND translation_status = 'failed'
            """,
            (template,),
        ).fetchone()["total"]
        ready_with_english = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id) AS total
            FROM article_ai_outputs
            WHERE format_template = ?
              AND translation_status = 'completed'
              AND COALESCE(translation_content_en, '') != ''
            """,
            (template,),
        ).fetchone()["total"]
    return {
        "completed_outputs": completed,
        "failed_outputs": failed,
        "running_outputs": running,
        "summary_completed": summary_completed,
        "summary_failed": summary_failed,
        "format_completed": format_completed,
        "format_failed": format_failed,
        "translation_completed": translation_completed,
        "translation_failed": translation_failed,
        "ready_with_english": ready_with_english,
    }


def run_all(*, worker_count: int, limit: int = 0, poll_seconds: int = DEFAULT_POLL_SECONDS, rebuild_manifest: bool = False) -> int:
    ensure_database_ready()
    ensure_runtime_tables()
    ensure_batch_directories()
    manifest = build_manifest(force=rebuild_manifest, limit=limit)
    run_meta = {
        "started_at": now_iso(),
        "status": "running",
        "model_name": RELAYOUT_MODEL,
        "format_template": RELAYOUT_TEMPLATE,
        "worker_count": worker_count,
        "manifest_article_count": len(manifest),
    }
    write_json_atomic(RUN_META_PATH, run_meta)
    processes = spawn_workers(worker_count=worker_count, limit=limit, rebuild_manifest=rebuild_manifest)
    orchestrator_state = {
        "started_at": run_meta["started_at"],
        "status": "running",
        "model_name": RELAYOUT_MODEL,
        "format_template": RELAYOUT_TEMPLATE,
        "worker_count": worker_count,
        "workers": [
            {
                "worker_name": item["worker_name"],
                "pid": item["pid"],
                "log_path": item["log_path"],
            }
            for item in processes
        ],
    }
    write_json_atomic(ORCHESTRATOR_STATE_PATH, orchestrator_state)

    try:
        while True:
            running_workers = 0
            worker_rows: list[dict[str, Any]] = []
            for item in processes:
                process: subprocess.Popen = item["process"]
                code = process.poll()
                if code is None:
                    running_workers += 1
                worker_rows.append(
                    {
                        "worker_name": item["worker_name"],
                        "pid": item["pid"],
                        "return_code": code,
                        "log_path": item["log_path"],
                    }
                )
            orchestrator_state["workers"] = worker_rows
            orchestrator_state["running_workers"] = running_workers
            orchestrator_state["updated_at"] = now_iso()
            orchestrator_state["db_status"] = collect_db_status()
            write_json_atomic(ORCHESTRATOR_STATE_PATH, orchestrator_state)
            if running_workers == 0:
                break
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        orchestrator_state["status"] = "interrupted"
        orchestrator_state["updated_at"] = now_iso()
        write_json_atomic(ORCHESTRATOR_STATE_PATH, orchestrator_state)
        for item in processes:
            process: subprocess.Popen = item["process"]
            if process.poll() is None:
                process.terminate()
        close_handles(processes)
        raise

    close_handles(processes)
    failed_workers = [row for row in orchestrator_state["workers"] if row["return_code"] not in (0, None)]
    db_status = collect_db_status()
    has_article_failures = db_status["failed_outputs"] > 0
    orchestrator_state["status"] = "completed_with_failures" if failed_workers or has_article_failures else "completed"
    orchestrator_state["finished_at"] = now_iso()
    orchestrator_state["db_status"] = db_status
    write_json_atomic(ORCHESTRATOR_STATE_PATH, orchestrator_state)

    run_meta["status"] = orchestrator_state["status"]
    run_meta["finished_at"] = orchestrator_state["finished_at"]
    run_meta["db_status"] = db_status
    write_json_atomic(RUN_META_PATH, run_meta)

    print(json.dumps({"run_meta": run_meta, "db_status": db_status}, ensure_ascii=False, indent=2))
    return 0 if not failed_workers and not has_article_failures else 1


def show_status() -> int:
    ensure_database_ready()
    ensure_runtime_tables()
    ensure_batch_directories()
    payload = {
        "db_status": collect_db_status(),
        "run_meta": json.loads(RUN_META_PATH.read_text(encoding="utf-8")) if RUN_META_PATH.exists() else None,
        "orchestrator_state": json.loads(ORCHESTRATOR_STATE_PATH.read_text(encoding="utf-8"))
        if ORCHESTRATOR_STATE_PATH.exists()
        else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "manifest":
        ensure_database_ready()
        ensure_runtime_tables()
        payload = build_manifest(force=args.rebuild, limit=args.limit)
        print(json.dumps({"article_count": len(payload)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-worker":
        return run_worker(
            shard_index=args.shard_index,
            total_shards=args.total_shards,
            limit=args.limit,
            rebuild_manifest=args.rebuild_manifest,
            worker_name=args.worker_name,
        )
    if args.command == "run-all":
        return run_all(
            worker_count=args.workers,
            limit=args.limit,
            poll_seconds=args.poll_seconds,
            rebuild_manifest=args.rebuild_manifest,
        )
    if args.command == "status":
        return show_status()
    raise BatchError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
