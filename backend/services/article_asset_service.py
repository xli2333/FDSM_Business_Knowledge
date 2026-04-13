from __future__ import annotations

import hashlib
import json
from datetime import datetime


def build_article_source_hash(article: dict) -> str:
    payload = {
        "id": article["id"],
        "title": article["title"],
        "excerpt": article.get("main_topic") or article.get("excerpt") or "",
        "content": article.get("content") or "",
        "locked": bool(article.get("access", {}).get("locked")),
        "access_level": article.get("access", {}).get("access_level") or article.get("access_level") or "public",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def upsert_article_translation(
    connection,
    *,
    article_id: int,
    language: str,
    source_hash: str,
    translated: dict[str, str],
    timestamp: str | None = None,
) -> str:
    stored_at = timestamp or now_iso()
    connection.execute(
        """
        INSERT INTO article_translations (
            article_id,
            target_lang,
            source_hash,
            title,
            excerpt,
            summary,
            content,
            model,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(article_id, target_lang, source_hash) DO UPDATE SET
            title = excluded.title,
            excerpt = excluded.excerpt,
            summary = excluded.summary,
            content = excluded.content,
            model = excluded.model,
            updated_at = excluded.updated_at
        """,
        (
            article_id,
            language,
            source_hash,
            translated["title"],
            translated.get("excerpt") or "",
            translated["summary"],
            translated["content"],
            translated["model"],
            stored_at,
            stored_at,
        ),
    )
    return stored_at
