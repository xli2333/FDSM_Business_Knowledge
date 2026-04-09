from __future__ import annotations

from backend.database import connection_scope
from backend.services.article_ai_output_service import get_article_ai_output_detail, preview_markdown
from backend.services.article_asset_service import build_article_source_hash, upsert_article_translation
from backend.services.ai_service import is_ai_enabled, translate_article_to_english
from backend.services.catalog_service import get_article_detail
from backend.services.content_localization import contains_cjk
from backend.services.display_markdown_service import (
    normalize_article_display_markdown,
    normalize_summary_display_markdown,
)
from backend.services.fudan_wechat_renderer import is_fudan_wechat_preview_html
from backend.services.summary_preview_service import is_summary_preview_html, render_summary_preview_html


def _resolve_translation_html(
    *,
    title: str,
    content_markdown: str,
    summary: str,
    source_url: str | None,
    stored_html: str | None,
) -> str | None:
    del title, content_markdown, summary, source_url
    html = str(stored_html or "").strip()
    if is_fudan_wechat_preview_html(html):
        return html
    return None


def _resolve_summary_html(*, title: str, summary: str, stored_html: str | None = None, language: str = "en") -> str | None:
    del title
    html = str(stored_html or "").strip()
    if is_summary_preview_html(html):
        return html
    return render_summary_preview_html(summary, language=language)


def _is_english_source_article(article: dict) -> bool:
    sample = " ".join(
        str(part or "").strip()
        for part in (
            article.get("title"),
            article.get("main_topic"),
            article.get("excerpt"),
            article.get("content"),
        )
        if str(part or "").strip()
    )
    if not sample:
        return False
    return not contains_cjk(sample[:4000])


def _build_passthrough_translation(article: dict, *, language: str) -> dict:
    excerpt = str(article.get("main_topic") or article.get("excerpt") or "").strip()
    content = normalize_article_display_markdown(article.get("content") or "", language)
    summary_source = excerpt or preview_markdown(article.get("content") or "", paragraph_limit=4, char_limit=900)
    summary_text = normalize_summary_display_markdown(summary_source, language)
    access_locked = bool(article.get("access", {}).get("locked"))
    html = _resolve_translation_html(
        title=article["title"],
        content_markdown=content,
        summary=summary_text,
        source_url=article.get("link"),
        stored_html=None if access_locked else article.get("html_wechat"),
    )
    return {
        "title": article["title"],
        "excerpt": excerpt,
        "summary": summary_text,
        "content": content,
        "summary_html": _resolve_summary_html(title=article["title"], summary=summary_text, language=language),
        "html_web": html,
        "html_wechat": html,
        "model": "source-pass-through",
    }


def get_article_translation(
    article_id: int,
    *,
    target_lang: str = "en",
    current_user_id: str | None = None,
    membership_profile: dict | None = None,
) -> dict:
    language = (target_lang or "").strip().lower()
    if language != "en":
        raise ValueError("Only English translation is currently supported.")

    article = get_article_detail(
        article_id,
        current_user_id=current_user_id,
        membership_profile=membership_profile,
    )
    precomputed = get_article_ai_output_detail(article_id)
    if precomputed.get("translation_ready") and precomputed.get("source_hash_matches_current"):
        full_content = str(precomputed.get("formatted_markdown_en") or precomputed.get("translation_content_en") or "")
        content = preview_markdown(full_content) if article.get("access", {}).get("locked") else full_content
        summary_text = normalize_summary_display_markdown(precomputed.get("translation_summary_en") or "", "en")
        content = normalize_article_display_markdown(content, "en")
        html = _resolve_translation_html(
            title=precomputed.get("translation_title_en") or article["title"],
            content_markdown=content,
            summary=summary_text,
            source_url=article.get("link"),
            stored_html=precomputed.get("html_wechat_en"),
        )
        return {
            "article_id": article_id,
            "language": language,
            "source_hash": precomputed.get("source_hash") or "",
            "title": precomputed.get("translation_title_en") or article["title"],
            "excerpt": precomputed.get("translation_excerpt_en") or "",
            "summary": summary_text,
            "summary_html": _resolve_summary_html(
                title=precomputed.get("translation_title_en") or article["title"],
                summary=summary_text,
                stored_html=precomputed.get("summary_html_en"),
                language=language,
            ),
            "content": content,
            "html_web": html,
            "html_wechat": html,
            "model": precomputed.get("translation_model") or "precomputed",
            "cached": True,
            "content_scope": "preview" if article.get("access", {}).get("locked") else "full",
            "access_locked": bool(article.get("access", {}).get("locked")),
            "updated_at": precomputed.get("updated_at"),
        }

    source_hash = build_article_source_hash(article)

    with connection_scope() as connection:
        cached_row = connection.execute(
            """
            SELECT title, excerpt, summary, content, model, created_at, updated_at
            FROM article_translations
            WHERE article_id = ? AND target_lang = ? AND source_hash = ?
            """,
            (article_id, language, source_hash),
        ).fetchone()
        if cached_row:
            summary_text = normalize_summary_display_markdown(cached_row["summary"], "en")
            content = preview_markdown(cached_row["content"]) if article.get("access", {}).get("locked") else cached_row["content"]
            content = normalize_article_display_markdown(content, "en")
            html = _resolve_translation_html(
                title=cached_row["title"],
                content_markdown=content,
                summary=summary_text,
                source_url=article.get("link"),
                stored_html=None,
            )
            return {
                "article_id": article_id,
                "language": language,
                "source_hash": source_hash,
                "title": cached_row["title"],
                "excerpt": cached_row["excerpt"] or "",
                "summary": summary_text,
                "summary_html": _resolve_summary_html(title=cached_row["title"], summary=summary_text, language=language),
                "content": content,
                "html_web": html,
                "html_wechat": html,
                "model": cached_row["model"],
                "cached": True,
                "content_scope": "preview" if article.get("access", {}).get("locked") else "full",
                "access_locked": bool(article.get("access", {}).get("locked")),
                "updated_at": cached_row["updated_at"] or cached_row["created_at"],
            }

        if _is_english_source_article(article):
            translated = _build_passthrough_translation(article, language=language)
            timestamp = upsert_article_translation(
                connection,
                article_id=article_id,
                language=language,
                source_hash=source_hash,
                translated={
                    "title": translated["title"],
                    "excerpt": translated["excerpt"],
                    "summary": translated["summary"],
                    "content": translated["content"],
                    "model": translated["model"],
                },
            )
            connection.commit()
            return {
                "article_id": article_id,
                "language": language,
                "source_hash": source_hash,
                "title": translated["title"],
                "excerpt": translated["excerpt"],
                "summary": translated["summary"],
                "summary_html": translated["summary_html"],
                "content": translated["content"],
                "html_web": translated["html_web"],
                "html_wechat": translated["html_wechat"],
                "model": translated["model"],
                "cached": False,
                "content_scope": "preview" if article.get("access", {}).get("locked") else "full",
                "access_locked": bool(article.get("access", {}).get("locked")),
                "updated_at": timestamp,
            }

    if not is_ai_enabled():
        raise RuntimeError("Gemini Flash translation is not configured.")

    try:
        translated = translate_article_to_english(
            article["title"],
            article.get("main_topic") or article.get("excerpt") or "",
            article.get("content") or "",
        )
    except Exception as exc:
        raise RuntimeError(
            "English translation is temporarily unavailable in the current runtime environment."
        ) from exc
    with connection_scope() as connection:
        timestamp = upsert_article_translation(
            connection,
            article_id=article_id,
            language=language,
            source_hash=source_hash,
            translated=translated,
        )
        connection.commit()

    content = preview_markdown(translated["content"]) if article.get("access", {}).get("locked") else translated["content"]
    content = normalize_article_display_markdown(content, "en")
    summary_text = normalize_summary_display_markdown(translated["summary"], "en")
    html = _resolve_translation_html(
        title=translated["title"],
        content_markdown=content,
        summary=summary_text,
        source_url=article.get("link"),
        stored_html=None,
    )
    return {
        "article_id": article_id,
        "language": language,
        "source_hash": source_hash,
        "title": translated["title"],
        "excerpt": translated["excerpt"],
        "summary": summary_text,
        "content": content,
        "summary_html": _resolve_summary_html(title=translated["title"], summary=summary_text, language=language),
        "html_web": html,
        "html_wechat": html,
        "model": translated["model"],
        "cached": False,
        "content_scope": "preview" if article.get("access", {}).get("locked") else "full",
        "access_locked": bool(article.get("access", {}).get("locked")),
        "updated_at": timestamp,
    }
