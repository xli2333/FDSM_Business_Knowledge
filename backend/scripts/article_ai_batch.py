from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    BUSINESS_DATA_DIR,
    GEMINI_API_KEYS,
    GEMINI_CHAT_MODEL,
    GEMINI_FLASH_MODEL,
    PRIMARY_GEMINI_KEY,
    resolve_gemini_model_name,
)
from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.services.article_asset_service import build_article_source_hash, now_iso, upsert_article_translation
from backend.services.html_renderer import render_editorial_package
from backend.services.summary_preview_service import render_summary_preview_html

BATCH_ROOT = BUSINESS_DATA_DIR / "article_ai_batch"
LOG_DIR = BATCH_ROOT / "logs"
STATE_DIR = BATCH_ROOT / "state"
MANIFEST_PATH = BATCH_ROOT / "manifest.json"
RUN_META_PATH = BATCH_ROOT / "run_meta.json"
ORCHESTRATOR_STATE_PATH = STATE_DIR / "orchestrator.json"

DEFAULT_WORKERS = 20
DEFAULT_POLL_SECONDS = 15
MAX_API_ATTEMPTS = 8
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 300
FORMAT_TEMPLATE = "fudan-business-knowledge-v1"
FLASH_MODEL = GEMINI_FLASH_MODEL or "gemini-2.5-flash"
CHAT_MODEL = GEMINI_CHAT_MODEL or FLASH_MODEL
TRANSLATION_MODEL_CHAIN = [FLASH_MODEL]
if CHAT_MODEL and CHAT_MODEL not in TRANSLATION_MODEL_CHAIN:
    TRANSLATION_MODEL_CHAIN.append(CHAT_MODEL)

TRANSLATION_FIELD_ALIASES = {
    "title": ("title", "english_title", "translated_title"),
    "excerpt": ("excerpt", "deck", "intro", "lead", "subtitle"),
    "summary": ("summary", "abstract", "overview", "brief"),
    "content": ("content", "body", "translation", "translated_content", "article"),
}

SUMMARY_PROMPT = """你是复旦商业知识编辑部的摘要助手。
请基于下面的中文商业文章生成一份高密度中文 Markdown 摘要。

要求：
1. 保留原文逻辑，不编造事实，不加入原文没有的新观点。
2. 以适合知识产品阅读的方式组织内容，优先用 5-8 个短标题或要点。
3. 语言要凝练、专业，避免空话。
4. 输出只包含 Markdown，不要解释。

标题：
{title}

文章正文：
{content}

摘要："""

FORMAT_PROMPT = """你是复旦商业知识编辑部的排版助手，请把下面的中文商业文章整理成适合“复旦商业知识”发布的 Markdown 稿件。

排版要求：
1. 保留全部关键事实、论点、案例与引语，不编造，不删除关键内容。
2. 在不改变原意的前提下，补出清晰的标题层级、导语、小标题、列表与引用。
3. 一级标题必须是文章标题。
4. 如果原文适合，加一个简短导语段；其余内容用二级、三级标题组织。
5. 采访、对话、演讲、案例文章要保留原有说话人和结构。
6. 不要输出 HTML，只输出 Markdown。
7. 风格参考“复旦商业知识 / AI_writer”的公众号长文可读性排版，重点是结构清晰、信息密度高、易于转成 Web/公众号模板。

元数据：
- 标题：{title}
- 摘要提示：{excerpt}
- 主话题：{main_topic}
- 文章类型：{article_type}
- 机构：{organization}
- 标签：{tags}

原文正文：
{content}

Markdown："""

TRANSLATION_PROMPT = """You are translating a Chinese business knowledge article into polished professional English for the Fudan Business Knowledge publication.

Requirements:
1. This translation task is independent from summary generation and formatting. Work only from the original Chinese source article.
2. Translate the full source article into English and preserve all meaningful content.
3. Preserve paragraph breaks and obvious list or quotation structure, but do not invent a publication layout that is not present in the source.
4. Also provide a short English deck and a concise English summary based on the source article itself.
5. Return strict JSON only with this shape:
{{
  "title": "English title",
  "excerpt": "English deck or short intro",
  "summary": "English Markdown summary",
  "content": "Full translated Markdown body"
}}

Source title:
{title}

Source excerpt:
{excerpt}

Source full Chinese article:
{content}

JSON:"""


class BatchError(Exception):
    """Raised when the batch pipeline cannot complete a task."""


def is_non_retryable_batch_error(exc: Exception) -> bool:
    text = str(exc)
    return text.startswith("NONRETRYABLE:")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch process article translation, summary, and formatting.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest", help="Build or rebuild the article manifest.")
    manifest_parser.add_argument("--limit", type=int, default=0)
    manifest_parser.add_argument("--rebuild", action="store_true")

    worker_parser = subparsers.add_parser("run-worker", help="Run one processing shard.")
    worker_parser.add_argument("--shard-index", type=int, required=True)
    worker_parser.add_argument("--total-shards", type=int, required=True)
    worker_parser.add_argument("--limit", type=int, default=0)
    worker_parser.add_argument("--rebuild-manifest", action="store_true")
    worker_parser.add_argument("--worker-name", type=str, default="")

    run_all_parser = subparsers.add_parser("run-all", help="Run the full multi-worker batch.")
    run_all_parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    run_all_parser.add_argument("--limit", type=int, default=0)
    run_all_parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    run_all_parser.add_argument("--rebuild-manifest", action="store_true")

    subparsers.add_parser("status", help="Show current batch status.")
    return parser.parse_args()


def ensure_batch_directories() -> None:
    for path in (BATCH_ROOT, LOG_DIR, STATE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def load_api_keys() -> list[str]:
    keys = [item.strip() for item in GEMINI_API_KEYS if item.strip()]
    if PRIMARY_GEMINI_KEY and PRIMARY_GEMINI_KEY not in keys:
        keys.insert(0, PRIMARY_GEMINI_KEY)
    if not keys:
        raise BatchError("No Gemini API keys are configured.")
    return keys


def make_logger(worker_name: str) -> logging.Logger:
    logger = logging.getLogger(f"article-ai-batch.{worker_name}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def worker_state_path(worker_name: str) -> Path:
    return STATE_DIR / f"{worker_name}.json"


def build_manifest(*, force: bool = False, limit: int = 0) -> list[dict[str, Any]]:
    ensure_batch_directories()
    if MANIFEST_PATH.exists() and not force and limit <= 0:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return payload["articles"]

    safe_limit = max(limit, 0)
    with connection_scope() as connection:
        query = """
            SELECT id, doc_id, slug, relative_path, title, publish_date
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
    ]
    payload = {
        "generated_at": now_iso(),
        "model_name": FLASH_MODEL,
        "article_count": len(articles),
        "articles": articles,
    }
    if safe_limit <= 0:
        write_json_atomic(MANIFEST_PATH, payload)
    return articles


def fetch_article(connection, article_id: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            id,
            doc_id,
            slug,
            relative_path,
            title,
            publish_date,
            link,
            content,
            excerpt,
            main_topic,
            article_type,
            primary_org_name,
            access_level
        FROM articles
        WHERE id = ?
        """,
        (article_id,),
    ).fetchone()
    if row is None:
        raise BatchError(f"Article {article_id} was not found.")
    return dict(row)


def fetch_article_tags(connection, article_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT t.name, t.slug, t.category, t.color, at.confidence
        FROM article_tags at
        JOIN tags t ON t.id = at.tag_id
        WHERE at.article_id = ?
        ORDER BY at.confidence DESC, t.article_count DESC, t.name ASC
        LIMIT 8
        """,
        (article_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def parse_json_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise BatchError("Model did not return a JSON object.")
        try:
            payload = json.loads(text[first : last + 1])
        except json.JSONDecodeError as exc:
            raise BatchError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise BatchError("Model JSON root is not an object.")
    return payload


def stringify_translation_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [stringify_translation_value(item) for item in value]
        return "\n\n".join(part for part in parts if part)
    if isinstance(value, dict):
        ordered_keys = ("text", "content", "summary", "body", "title")
        parts = [stringify_translation_value(value.get(key)) for key in ordered_keys if value.get(key) is not None]
        cleaned = [part for part in parts if part]
        if cleaned:
            return "\n\n".join(cleaned)
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def normalize_translation_payload(payload: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for target_key, aliases in TRANSLATION_FIELD_ALIASES.items():
        for alias in aliases:
            value = stringify_translation_value(payload.get(alias))
            if value:
                normalized[target_key] = value
                break
    return normalized


def decode_jsonish_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return (
            value.replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
            .strip()
        )


def extract_jsonish_field(text: str, alias: str) -> str:
    quoted_patterns = [
        rf'"{re.escape(alias)}"\s*:\s*"(?P<value>(?:[^"\\]|\\.|[\r\n])*)"',
        rf"'{re.escape(alias)}'\s*:\s*'(?P<value>(?:[^'\\]|\\.|[\r\n])*)'",
    ]
    for pattern in quoted_patterns:
        match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
        if match:
            return decode_jsonish_string(match.group("value").strip())

    label_patterns = [
        rf"^(?:{re.escape(alias)}|{re.escape(alias).title()})\s*:\s*(?P<value>.+)$",
    ]
    for pattern in label_patterns:
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            return match.group("value").strip()
    return ""


def extract_translation_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    parse_error: Exception | None = None
    try:
        payload = normalize_translation_payload(parse_json_payload(text))
        if any(payload.values()):
            return payload
    except BatchError as exc:
        parse_error = exc

    payload: dict[str, str] = {}
    for target_key, aliases in TRANSLATION_FIELD_ALIASES.items():
        for alias in aliases:
            value = extract_jsonish_field(text, alias)
            if value:
                payload[target_key] = value
                break
    if any(payload.values()):
        return payload

    if len(text) >= 400 and not text.lstrip().startswith("{"):
        return {"content": text}

    if parse_error is not None:
        raise parse_error
    raise BatchError("Model did not return a JSON object.")


def request_gemini_text(
    *,
    prompt: str,
    api_keys: list[str],
    key_offset: int,
    logger: logging.Logger,
    worker_name: str,
    response_mime_type: str = "text/plain",
    model_name: str | None = None,
) -> str:
    session = requests.Session()
    last_error: Exception | None = None
    last_text = ""
    target_model = resolve_gemini_model_name((model_name or FLASH_MODEL).strip() or FLASH_MODEL)
    for attempt in range(MAX_API_ATTEMPTS):
        key = api_keys[(key_offset + attempt) % len(api_keys)]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": response_mime_type,
            },
        }
        try:
            response = session.post(
                url,
                json=payload,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            )
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates") or []
                if not candidates:
                    raise BatchError(f"No candidates in Gemini response: {data}")
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    finish_reason = str(candidates[0].get("finishReason") or "").strip().upper()
                    if finish_reason in {"RECITATION", "SAFETY"}:
                        raise BatchError(f"NONRETRYABLE: No content parts in Gemini response: {data}")
                    raise BatchError(f"No content parts in Gemini response: {data}")
                last_text = parts[0].get("text", "").strip()
                if not last_text:
                    raise BatchError("Gemini returned an empty body.")
                return last_text
            if response.status_code in {429, 500, 502, 503, 504}:
                sleep_seconds = min(60, 2**attempt + random.uniform(0.2, 1.2))
                logger.warning(
                    "%s retryable Gemini error %s on attempt %s/%s; sleeping %.1fs",
                    worker_name,
                    response.status_code,
                    attempt + 1,
                    MAX_API_ATTEMPTS,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)
                continue
            raise BatchError(f"Gemini API error {response.status_code}: {response.text}")
        except (requests.RequestException, BatchError) as exc:
            last_error = exc
            if is_non_retryable_batch_error(exc):
                break
            if attempt == MAX_API_ATTEMPTS - 1:
                break
            sleep_seconds = min(45, 1.5**attempt + random.uniform(0.1, 0.8))
            logger.warning(
                "%s request failure on attempt %s/%s: %s; sleeping %.1fs",
                worker_name,
                attempt + 1,
                MAX_API_ATTEMPTS,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
    raise BatchError(f"Gemini request failed after {MAX_API_ATTEMPTS} attempts: {last_error or last_text}")


def generate_summary_markdown(
    article: dict[str, Any],
    *,
    api_keys: list[str],
    key_offset: int,
    logger: logging.Logger,
    worker_name: str,
) -> str:
    prompt = SUMMARY_PROMPT.format(title=article["title"], content=article["content"])
    return request_gemini_text(
        prompt=prompt,
        api_keys=api_keys,
        key_offset=key_offset,
        logger=logger,
        worker_name=worker_name,
    )


def generate_formatted_markdown(
    article: dict[str, Any],
    *,
    tags: list[dict[str, Any]],
    api_keys: list[str],
    key_offset: int,
    logger: logging.Logger,
    worker_name: str,
) -> str:
    prompt = FORMAT_PROMPT.format(
        title=article["title"],
        excerpt=article.get("excerpt") or "",
        main_topic=article.get("main_topic") or "",
        article_type=article.get("article_type") or "",
        organization=article.get("primary_org_name") or "",
        tags=", ".join(tag["name"] for tag in tags) or "",
        content=article["content"],
    )
    return request_gemini_text(
        prompt=prompt,
        api_keys=api_keys,
        key_offset=key_offset,
        logger=logger,
        worker_name=worker_name,
    )


def clean_model_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def english_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for chunk in re.split(r"\n\s*\n", clean_model_fence(text)):
        item = chunk.strip()
        if not item:
            continue
        normalized = re.sub(r"^#+\s*", "", item).strip()
        if normalized:
            paragraphs.append(normalized)
    return paragraphs


def derive_translation_excerpt(content: str, *, limit: int = 220) -> str:
    for paragraph in english_paragraphs(content):
        compact = re.sub(r"\s+", " ", paragraph).strip()
        if not compact:
            continue
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."
    return ""


def derive_translation_summary(content: str, excerpt: str) -> str:
    selected: list[str] = []
    compact_excerpt = re.sub(r"\s+", " ", excerpt).strip()
    if compact_excerpt:
        selected.append(compact_excerpt)
    for paragraph in english_paragraphs(content):
        compact = re.sub(r"\s+", " ", paragraph).strip()
        if not compact or compact in selected:
            continue
        selected.append(compact)
        if len(selected) >= 3:
            break
    return "\n\n".join(selected).strip()


def finalize_translation_payload(article: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    title = stringify_translation_value(payload.get("title")) or article["title"]
    content = clean_model_fence(stringify_translation_value(payload.get("content")))
    if not content:
        raise BatchError("Translation payload is missing content.")

    excerpt = stringify_translation_value(payload.get("excerpt"))
    if not excerpt:
        excerpt = derive_translation_excerpt(content) or (article.get("main_topic") or article.get("excerpt") or article["title"])

    summary = clean_model_fence(stringify_translation_value(payload.get("summary")))
    if not summary:
        summary = derive_translation_summary(content, excerpt)
    if not summary:
        raise BatchError("Translation payload is missing summary or content.")

    return {
        "title": title,
        "excerpt": excerpt,
        "summary": summary,
        "content": content,
    }


def translate_full_article_to_english(
    article: dict[str, Any],
    *,
    api_keys: list[str],
    key_offset: int,
    logger: logging.Logger,
    worker_name: str,
) -> dict[str, str]:
    prompt = TRANSLATION_PROMPT.format(
        title=article["title"],
        excerpt=article.get("main_topic") or article.get("excerpt") or "",
        content=article["content"],
    )
    last_error: Exception | None = None
    for model_index, model_name in enumerate(TRANSLATION_MODEL_CHAIN):
        try:
            raw = request_gemini_text(
                prompt=prompt,
                api_keys=api_keys,
                key_offset=key_offset + model_index * 17,
                logger=logger,
                worker_name=worker_name,
                response_mime_type="application/json",
                model_name=model_name,
            )
            payload = extract_translation_payload(raw)
            translated = finalize_translation_payload(article, payload)
            translated["model"] = model_name
            return translated
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "%s translation fallback failed for article %s with model %s: %s",
                worker_name,
                article["id"],
                model_name,
                exc,
            )
    raise BatchError(str(last_error) if last_error else "Translation failed without a concrete error.")


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
    summary_zh: str | None = None,
    formatted_markdown_zh: str | None = None,
    translated: dict[str, str] | None = None,
    tags: list[dict[str, Any]],
) -> dict[str, str]:
    source_url = article.get("link") or None
    rendered: dict[str, str] = {}
    if summary_zh:
        rendered["summary_html_zh"] = render_summary_preview_html(summary_zh, language="zh") or ""
    if formatted_markdown_zh:
        zh_article = build_render_payload(
            article,
            title=article["title"],
            excerpt=summary_zh or article.get("excerpt") or article.get("main_topic") or "",
            content_markdown=formatted_markdown_zh,
            source_url=source_url,
            organization="复旦商业知识库",
            author="复旦商业知识库编辑部",
        )
        zh_rendered = render_editorial_package(zh_article, tags, language="zh-CN")
        rendered["html_web_zh"] = zh_rendered["html_web"]
        rendered["html_wechat_zh"] = zh_rendered["html_wechat"]
    if translated and translated.get("content"):
        rendered["summary_html_en"] = render_summary_preview_html(translated.get("summary") or "", language="en") or ""
        en_article = build_render_payload(
            article,
            title=translated["title"],
            excerpt=translated.get("excerpt") or translated.get("summary") or "",
            content_markdown=translated["content"],
            source_url=source_url,
            organization="Fudan Business Knowledge",
            author="Fudan Business Knowledge Editorial Desk",
            subtitle="",
        )
        en_rendered = render_editorial_package(en_article, [], language="en")
        rendered["html_web_en"] = en_rendered["html_web"]
        rendered["html_wechat_en"] = en_rendered["html_wechat"]
    return rendered


def upsert_running_record(
    connection,
    *,
    article: dict[str, Any],
    source_hash: str,
    worker_name: str,
    started_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO article_ai_outputs (
            article_id,
            doc_id,
            slug,
            relative_path,
            source_hash,
            source_title,
            source_excerpt,
            status,
            worker_name,
            started_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?)
        ON CONFLICT(article_id, source_hash) DO UPDATE SET
            doc_id = excluded.doc_id,
            slug = excluded.slug,
            relative_path = excluded.relative_path,
            source_title = excluded.source_title,
            source_excerpt = excluded.source_excerpt,
            status = 'running',
            error_message = NULL,
            worker_name = excluded.worker_name,
            started_at = excluded.started_at,
            updated_at = excluded.updated_at
        """,
        (
            article["id"],
            article.get("doc_id"),
            article.get("slug"),
            article.get("relative_path"),
            source_hash,
            article["title"],
            article.get("excerpt") or article.get("main_topic") or "",
            worker_name,
            started_at,
            started_at,
            started_at,
        ),
    )


def upsert_failed_record(
    connection,
    *,
    article: dict[str, Any],
    source_hash: str,
    worker_name: str,
    started_at: str,
    error_message: str,
) -> None:
    failed_at = now_iso()
    connection.execute(
        """
        INSERT INTO article_ai_outputs (
            article_id,
            doc_id,
            slug,
            relative_path,
            source_hash,
            source_title,
            source_excerpt,
            status,
            error_message,
            worker_name,
            started_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', ?, ?, ?, ?, ?)
        ON CONFLICT(article_id, source_hash) DO UPDATE SET
            doc_id = excluded.doc_id,
            slug = excluded.slug,
            relative_path = excluded.relative_path,
            source_title = excluded.source_title,
            source_excerpt = excluded.source_excerpt,
            status = 'failed',
            error_message = excluded.error_message,
            worker_name = excluded.worker_name,
            started_at = excluded.started_at,
            updated_at = excluded.updated_at
        """,
        (
            article["id"],
            article.get("doc_id"),
            article.get("slug"),
            article.get("relative_path"),
            source_hash,
            article["title"],
            article.get("excerpt") or article.get("main_topic") or "",
            error_message[:4000],
            worker_name,
            started_at,
            started_at,
            failed_at,
        ),
    )


def persist_completed_outputs(
    connection,
    *,
    article: dict[str, Any],
    source_hash: str,
    summary_zh: str,
    formatted_markdown_zh: str,
    translated: dict[str, str],
    rendered: dict[str, str],
    worker_name: str,
    started_at: str,
) -> str:
    timestamp = upsert_article_translation(
        connection,
        article_id=article["id"],
        language="en",
        source_hash=source_hash,
        translated=translated,
        timestamp=now_iso(),
    )
    connection.execute(
        """
        INSERT INTO article_ai_outputs (
            article_id,
            doc_id,
            slug,
            relative_path,
            source_hash,
            source_title,
            source_excerpt,
            summary_zh,
            summary_html_zh,
            summary_model,
            formatted_markdown_zh,
            formatted_markdown_en,
            html_web_zh,
            html_wechat_zh,
            summary_html_en,
            html_web_en,
            html_wechat_en,
            translation_model,
            format_model,
            format_template,
            status,
            error_message,
            worker_name,
            started_at,
            completed_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', NULL, ?, ?, ?, ?, ?)
        ON CONFLICT(article_id, source_hash) DO UPDATE SET
            doc_id = excluded.doc_id,
            slug = excluded.slug,
            relative_path = excluded.relative_path,
            source_title = excluded.source_title,
            source_excerpt = excluded.source_excerpt,
            summary_zh = excluded.summary_zh,
            summary_html_zh = excluded.summary_html_zh,
            summary_model = excluded.summary_model,
            formatted_markdown_zh = excluded.formatted_markdown_zh,
            formatted_markdown_en = excluded.formatted_markdown_en,
            html_web_zh = excluded.html_web_zh,
            html_wechat_zh = excluded.html_wechat_zh,
            summary_html_en = excluded.summary_html_en,
            html_web_en = excluded.html_web_en,
            html_wechat_en = excluded.html_wechat_en,
            translation_model = excluded.translation_model,
            format_model = excluded.format_model,
            format_template = excluded.format_template,
            status = 'completed',
            error_message = NULL,
            worker_name = excluded.worker_name,
            started_at = excluded.started_at,
            completed_at = excluded.completed_at,
            updated_at = excluded.updated_at
        """,
        (
            article["id"],
            article.get("doc_id"),
            article.get("slug"),
            article.get("relative_path"),
            source_hash,
            article["title"],
            article.get("excerpt") or article.get("main_topic") or "",
            summary_zh,
            rendered.get("summary_html_zh"),
            FLASH_MODEL,
            formatted_markdown_zh,
            translated["content"],
            rendered["html_web_zh"],
            rendered["html_wechat_zh"],
            rendered.get("summary_html_en"),
            rendered["html_web_en"],
            rendered["html_wechat_en"],
            translated["model"],
            FLASH_MODEL,
            FORMAT_TEMPLATE,
            worker_name,
            started_at,
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    return timestamp


OUTPUT_UPSERT_COLUMNS = [
    "article_id",
    "doc_id",
    "slug",
    "relative_path",
    "source_hash",
    "source_lang",
    "target_lang",
    "source_title",
    "source_excerpt",
    "summary_zh",
    "summary_html_zh",
    "summary_model",
    "formatted_markdown_zh",
    "formatted_markdown_en",
    "translation_title_en",
    "translation_excerpt_en",
    "translation_summary_en",
    "summary_html_en",
    "translation_content_en",
    "html_web_zh",
    "html_wechat_zh",
    "html_web_en",
    "html_wechat_en",
    "summary_status",
    "format_status",
    "translation_status",
    "summary_error",
    "format_error",
    "translation_error",
    "translation_model",
    "format_model",
    "format_template",
    "status",
    "error_message",
    "worker_name",
    "started_at",
    "completed_at",
    "created_at",
    "updated_at",
]


def truncate_task_error(message: Any) -> str | None:
    if not message:
        return None
    return str(message)[:4000]


def normalize_output_row(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(row) if row else {}

    summary_ready = bool(str(payload.get("summary_zh") or "").strip())
    format_ready = bool(str(payload.get("formatted_markdown_zh") or "").strip())
    translation_ready = bool(str(payload.get("translation_content_en") or "").strip())

    summary_status = str(payload.get("summary_status") or "").strip() or ("completed" if summary_ready else "pending")
    format_status = str(payload.get("format_status") or "").strip() or ("completed" if format_ready else "pending")
    translation_status = str(payload.get("translation_status") or "").strip() or (
        "completed" if translation_ready else "pending"
    )

    if summary_status == "completed" and not summary_ready:
        summary_status = "pending"
    if format_status == "completed" and not format_ready:
        format_status = "pending"
    if translation_status == "completed" and not translation_ready:
        translation_status = "pending"

    payload["summary_status"] = summary_status
    payload["format_status"] = format_status
    payload["translation_status"] = translation_status
    return payload


def is_summary_complete(row: dict[str, Any]) -> bool:
    return row.get("summary_status") == "completed" and bool(str(row.get("summary_zh") or "").strip())


def is_format_complete(row: dict[str, Any]) -> bool:
    return row.get("format_status") == "completed" and bool(str(row.get("formatted_markdown_zh") or "").strip())


def extract_completed_translation(row: dict[str, Any]) -> dict[str, str] | None:
    if row.get("translation_status") != "completed":
        return None
    content = str(row.get("translation_content_en") or "").strip()
    if not content:
        return None
    return {
        "title": str(row.get("translation_title_en") or row.get("source_title") or "").strip(),
        "excerpt": str(row.get("translation_excerpt_en") or "").strip(),
        "summary": str(row.get("translation_summary_en") or "").strip(),
        "content": content,
        "model": str(row.get("translation_model") or FLASH_MODEL).strip() or FLASH_MODEL,
    }


def derive_output_status(row: dict[str, Any]) -> str:
    task_statuses = [
        row.get("summary_status") or "pending",
        row.get("format_status") or "pending",
        row.get("translation_status") or "pending",
    ]
    if all(status == "completed" for status in task_statuses):
        return "completed"
    if "running" in task_statuses:
        return "running"
    if "failed" in task_statuses:
        return "failed"
    if "completed" in task_statuses:
        return "partial"
    return "pending"


def derive_error_message(row: dict[str, Any]) -> str | None:
    errors: list[str] = []
    for label, status_key, error_key in (
        ("summary", "summary_status", "summary_error"),
        ("format", "format_status", "format_error"),
        ("translation", "translation_status", "translation_error"),
    ):
        if row.get(status_key) == "failed" and row.get(error_key):
            errors.append(f"{label}: {row[error_key]}")
    if not errors:
        return None
    return truncate_task_error(" | ".join(errors))


def upsert_output_snapshot(
    connection,
    *,
    article: dict[str, Any],
    source_hash: str,
    worker_name: str,
    started_at: str,
    updates: dict[str, Any] | None = None,
    force_status: str | None = None,
) -> dict[str, Any]:
    existing_row = connection.execute(
        """
        SELECT *
        FROM article_ai_outputs
        WHERE article_id = ? AND source_hash = ?
        """,
        (article["id"], source_hash),
    ).fetchone()
    existing = normalize_output_row(existing_row)

    row: dict[str, Any] = {
        "article_id": article["id"],
        "doc_id": article.get("doc_id"),
        "slug": article.get("slug"),
        "relative_path": article.get("relative_path"),
        "source_hash": source_hash,
        "source_lang": "zh-CN",
        "target_lang": "en",
        "source_title": article["title"],
        "source_excerpt": article.get("excerpt") or article.get("main_topic") or "",
        "summary_zh": None,
        "summary_html_zh": None,
        "summary_model": None,
        "formatted_markdown_zh": None,
        "formatted_markdown_en": None,
        "translation_title_en": None,
        "translation_excerpt_en": None,
        "translation_summary_en": None,
        "summary_html_en": None,
        "translation_content_en": None,
        "html_web_zh": None,
        "html_wechat_zh": None,
        "html_web_en": None,
        "html_wechat_en": None,
        "summary_status": "pending",
        "format_status": "pending",
        "translation_status": "pending",
        "summary_error": None,
        "format_error": None,
        "translation_error": None,
        "translation_model": None,
        "format_model": None,
        "format_template": FORMAT_TEMPLATE,
        "status": "pending",
        "error_message": None,
        "worker_name": worker_name,
        "started_at": started_at,
        "completed_at": None,
        "created_at": existing.get("created_at") or started_at,
        "updated_at": now_iso(),
    }
    row.update(existing)
    row.update(
        {
            "article_id": article["id"],
            "doc_id": article.get("doc_id"),
            "slug": article.get("slug"),
            "relative_path": article.get("relative_path"),
            "source_hash": source_hash,
            "source_lang": "zh-CN",
            "target_lang": "en",
            "source_title": article["title"],
            "source_excerpt": article.get("excerpt") or article.get("main_topic") or "",
            "format_template": FORMAT_TEMPLATE,
            "worker_name": worker_name,
            "started_at": started_at,
            "created_at": existing.get("created_at") or started_at,
        }
    )
    if updates:
        row.update(updates)

    row["summary_error"] = truncate_task_error(row.get("summary_error"))
    row["format_error"] = truncate_task_error(row.get("format_error"))
    row["translation_error"] = truncate_task_error(row.get("translation_error"))
    if row.get("translation_content_en") and not row.get("formatted_markdown_en"):
        row["formatted_markdown_en"] = row["translation_content_en"]

    row.update(normalize_output_row(row))

    status = force_status or derive_output_status(row)
    row["status"] = status
    row["error_message"] = derive_error_message(row)
    row["updated_at"] = now_iso()
    row["completed_at"] = row.get("completed_at") or row["updated_at"] if status == "completed" else None

    columns_sql = ", ".join(OUTPUT_UPSERT_COLUMNS)
    placeholders_sql = ", ".join("?" for _ in OUTPUT_UPSERT_COLUMNS)
    update_columns = [column for column in OUTPUT_UPSERT_COLUMNS if column not in {"article_id", "source_hash", "created_at"}]
    updates_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    connection.execute(
        f"""
        INSERT INTO article_ai_outputs ({columns_sql})
        VALUES ({placeholders_sql})
        ON CONFLICT(article_id, source_hash) DO UPDATE SET
            {updates_sql}
        """,
        [row.get(column) for column in OUTPUT_UPSERT_COLUMNS],
    )
    return row


def persist_translation_snapshot(
    connection,
    *,
    article: dict[str, Any],
    source_hash: str,
    translated: dict[str, str],
    worker_name: str,
    started_at: str,
    force_status: str | None = None,
) -> dict[str, Any]:
    upsert_article_translation(
        connection,
        article_id=article["id"],
        language="en",
        source_hash=source_hash,
        translated=translated,
        timestamp=now_iso(),
    )
    return upsert_output_snapshot(
        connection,
        article=article,
        source_hash=source_hash,
        worker_name=worker_name,
        started_at=started_at,
        updates={
            "translation_title_en": translated["title"],
            "translation_excerpt_en": translated["excerpt"],
            "translation_summary_en": translated["summary"],
            "translation_content_en": translated["content"],
            "formatted_markdown_en": translated["content"],
            "translation_model": translated["model"],
            "translation_status": "completed",
            "translation_error": None,
        },
        force_status=force_status,
    )


def persist_rendered_snapshot(
    connection,
    *,
    article: dict[str, Any],
    source_hash: str,
    rendered: dict[str, str],
    worker_name: str,
    started_at: str,
    force_status: str | None = None,
) -> dict[str, Any]:
    updates = {key: value for key, value in rendered.items() if value}
    return upsert_output_snapshot(
        connection,
        article=article,
        source_hash=source_hash,
        worker_name=worker_name,
        started_at=started_at,
        updates=updates,
        force_status=force_status,
    )


def run_write_transaction(callback, *, retries: int = 6, logger: logging.Logger | None = None) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with connection_scope() as connection:
                result = callback(connection)
                connection.commit()
                return result
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" not in str(exc).lower() or attempt == retries - 1:
                break
            sleep_seconds = min(10, 0.5 * (attempt + 1))
            if logger:
                logger.warning("SQLite is locked; retrying in %.1fs", sleep_seconds)
            time.sleep(sleep_seconds)
    raise BatchError(f"SQLite write failed: {last_error}")


def process_article(
    article_id: int,
    *,
    worker_name: str,
    api_keys: list[str],
    sequence_index: int,
    logger: logging.Logger,
) -> str:
    with connection_scope() as connection:
        article = fetch_article(connection, article_id)
        tags = fetch_article_tags(connection, article_id)

    source_hash = build_article_source_hash(article)
    started_at = now_iso()

    with connection_scope() as connection:
        existing_row = connection.execute(
            """
            SELECT *
            FROM article_ai_outputs
            WHERE article_id = ? AND source_hash = ?
            """,
            (article_id, source_hash),
        ).fetchone()
    existing = normalize_output_row(existing_row)
    summary_zh = existing.get("summary_zh") if is_summary_complete(existing) else None
    formatted_markdown_zh = existing.get("formatted_markdown_zh") if is_format_complete(existing) else None
    translated = extract_completed_translation(existing)

    if summary_zh and formatted_markdown_zh and translated:
        return "skipped"

    run_write_transaction(
        lambda connection: upsert_output_snapshot(
            connection,
            article=article,
            source_hash=source_hash,
            worker_name=worker_name,
            started_at=started_at,
            force_status="running",
        ),
        logger=logger,
    )

    task_errors: list[str] = []

    if not summary_zh:
        run_write_transaction(
            lambda connection: upsert_output_snapshot(
                connection,
                article=article,
                source_hash=source_hash,
                worker_name=worker_name,
                started_at=started_at,
                updates={
                    "summary_status": "running",
                    "summary_error": None,
                },
                force_status="running",
            ),
            logger=logger,
        )
        try:
            summary_zh = generate_summary_markdown(
                article,
                api_keys=api_keys,
                key_offset=sequence_index * 11,
                logger=logger,
                worker_name=worker_name,
            )
            run_write_transaction(
                lambda connection: upsert_output_snapshot(
                    connection,
                    article=article,
                    source_hash=source_hash,
                    worker_name=worker_name,
                    started_at=started_at,
                    updates={
                        "summary_zh": summary_zh,
                        "summary_model": FLASH_MODEL,
                        "summary_status": "completed",
                        "summary_error": None,
                    },
                    force_status="running",
                ),
                logger=logger,
            )
        except Exception as exc:  # noqa: BLE001
            task_errors.append(f"summary: {exc}")
            run_write_transaction(
                lambda connection: upsert_output_snapshot(
                    connection,
                    article=article,
                    source_hash=source_hash,
                    worker_name=worker_name,
                    started_at=started_at,
                    updates={
                        "summary_status": "failed",
                        "summary_error": str(exc),
                        "summary_zh": None,
                    },
                    force_status="running",
                ),
                logger=logger,
            )
    
    if not formatted_markdown_zh:
        run_write_transaction(
            lambda connection: upsert_output_snapshot(
                connection,
                article=article,
                source_hash=source_hash,
                worker_name=worker_name,
                started_at=started_at,
                updates={
                    "format_status": "running",
                    "format_error": None,
                    "formatted_markdown_zh": None,
                    "html_web_zh": None,
                    "html_wechat_zh": None,
                },
                force_status="running",
            ),
            logger=logger,
        )
        try:
            formatted_markdown_zh = generate_formatted_markdown(
                article,
                tags=tags,
                api_keys=api_keys,
                key_offset=sequence_index * 11 + 1,
                logger=logger,
                worker_name=worker_name,
            )
            run_write_transaction(
                lambda connection: upsert_output_snapshot(
                    connection,
                    article=article,
                    source_hash=source_hash,
                    worker_name=worker_name,
                    started_at=started_at,
                    updates={
                        "formatted_markdown_zh": formatted_markdown_zh,
                        "format_model": FLASH_MODEL,
                        "format_status": "completed",
                        "format_error": None,
                    },
                    force_status="running",
                ),
                logger=logger,
            )
        except Exception as exc:  # noqa: BLE001
            task_errors.append(f"format: {exc}")
            run_write_transaction(
                lambda connection: upsert_output_snapshot(
                    connection,
                    article=article,
                    source_hash=source_hash,
                    worker_name=worker_name,
                    started_at=started_at,
                    updates={
                        "format_status": "failed",
                        "format_error": str(exc),
                        "formatted_markdown_zh": None,
                        "html_web_zh": None,
                        "html_wechat_zh": None,
                    },
                    force_status="running",
                ),
                logger=logger,
            )

    if not translated:
        run_write_transaction(
            lambda connection: upsert_output_snapshot(
                connection,
                article=article,
                source_hash=source_hash,
                worker_name=worker_name,
                started_at=started_at,
                updates={
                    "translation_status": "running",
                    "translation_error": None,
                    "translation_title_en": None,
                    "translation_excerpt_en": None,
                    "translation_summary_en": None,
                    "translation_content_en": None,
                    "formatted_markdown_en": None,
                    "html_web_en": None,
                    "html_wechat_en": None,
                },
                force_status="running",
            ),
            logger=logger,
        )
        try:
            translated = translate_full_article_to_english(
                article,
                api_keys=api_keys,
                key_offset=sequence_index * 11 + 2,
                logger=logger,
                worker_name=worker_name,
            )
            run_write_transaction(
                lambda connection: persist_translation_snapshot(
                    connection,
                    article=article,
                    source_hash=source_hash,
                    translated=translated,
                    worker_name=worker_name,
                    started_at=started_at,
                    force_status="running",
                ),
                logger=logger,
            )
        except Exception as exc:  # noqa: BLE001
            task_errors.append(f"translation: {exc}")
            run_write_transaction(
                lambda connection: upsert_output_snapshot(
                    connection,
                    article=article,
                    source_hash=source_hash,
                    worker_name=worker_name,
                    started_at=started_at,
                    updates={
                        "translation_status": "failed",
                        "translation_error": str(exc),
                        "translation_title_en": None,
                        "translation_excerpt_en": None,
                        "translation_summary_en": None,
                        "translation_content_en": None,
                        "formatted_markdown_en": None,
                        "html_web_en": None,
                        "html_wechat_en": None,
                    },
                    force_status="running",
                ),
                logger=logger,
            )

    rendered = render_variants(
        article,
        summary_zh=summary_zh,
        formatted_markdown_zh=formatted_markdown_zh,
        translated=translated,
        tags=tags,
    )
    if rendered:
        run_write_transaction(
            lambda connection: persist_rendered_snapshot(
                connection,
                article=article,
                source_hash=source_hash,
                rendered=rendered,
                worker_name=worker_name,
                started_at=started_at,
                force_status="running",
            ),
            logger=logger,
        )

    final_row = run_write_transaction(
        lambda connection: upsert_output_snapshot(
            connection,
            article=article,
            source_hash=source_hash,
            worker_name=worker_name,
            started_at=started_at,
        ),
        logger=logger,
    )
    if final_row["status"] == "completed":
        return "completed"
    raise BatchError(final_row.get("error_message") or " | ".join(task_errors) or "Article AI tasks did not complete.")


def run_worker(*, shard_index: int, total_shards: int, limit: int = 0, rebuild_manifest: bool = False, worker_name: str = "") -> int:
    ensure_database_ready()
    ensure_runtime_tables()
    ensure_batch_directories()
    api_keys = load_api_keys()
    safe_worker_name = worker_name or f"worker_{shard_index + 1:02d}"
    logger = make_logger(safe_worker_name)
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


def worker_log_path(worker_name: str) -> Path:
    return LOG_DIR / f"{worker_name}.log"


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
    with connection_scope() as connection:
        completed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE status = 'completed'"
        ).fetchone()["total"]
        failed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE status = 'failed'"
        ).fetchone()["total"]
        running = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE status = 'running'"
        ).fetchone()["total"]
        translations = connection.execute(
            "SELECT COUNT(*) AS total FROM article_translations WHERE target_lang = 'en'"
        ).fetchone()["total"]
        summary_completed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE summary_status = 'completed'"
        ).fetchone()["total"]
        summary_failed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE summary_status = 'failed'"
        ).fetchone()["total"]
        format_completed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE format_status = 'completed'"
        ).fetchone()["total"]
        format_failed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE format_status = 'failed'"
        ).fetchone()["total"]
        translation_completed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE translation_status = 'completed'"
        ).fetchone()["total"]
        translation_failed = connection.execute(
            "SELECT COUNT(*) AS total FROM article_ai_outputs WHERE translation_status = 'failed'"
        ).fetchone()["total"]
    return {
        "completed_outputs": completed,
        "failed_outputs": failed,
        "running_outputs": running,
        "english_translations": translations,
        "summary_completed": summary_completed,
        "summary_failed": summary_failed,
        "format_completed": format_completed,
        "format_failed": format_failed,
        "translation_completed": translation_completed,
        "translation_failed": translation_failed,
    }


def run_all(*, worker_count: int, limit: int = 0, poll_seconds: int = DEFAULT_POLL_SECONDS, rebuild_manifest: bool = False) -> int:
    ensure_database_ready()
    ensure_runtime_tables()
    ensure_batch_directories()
    manifest = build_manifest(force=rebuild_manifest, limit=limit)
    run_meta = {
        "started_at": now_iso(),
        "status": "running",
        "model_name": FLASH_MODEL,
        "worker_count": worker_count,
        "manifest_article_count": len(manifest),
    }
    write_json_atomic(RUN_META_PATH, run_meta)
    processes = spawn_workers(worker_count=worker_count, limit=limit, rebuild_manifest=rebuild_manifest)
    orchestrator_state = {
        "started_at": run_meta["started_at"],
        "status": "running",
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
    orchestrator_state["status"] = "completed_with_failures" if failed_workers else "completed"
    orchestrator_state["finished_at"] = now_iso()
    orchestrator_state["db_status"] = db_status
    write_json_atomic(ORCHESTRATOR_STATE_PATH, orchestrator_state)

    run_meta["status"] = orchestrator_state["status"]
    run_meta["finished_at"] = orchestrator_state["finished_at"]
    run_meta["db_status"] = db_status
    write_json_atomic(RUN_META_PATH, run_meta)

    print(json.dumps({"run_meta": run_meta, "db_status": db_status}, ensure_ascii=False, indent=2))
    return 0


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
