from __future__ import annotations

from datetime import datetime
import re

from fastapi import HTTPException

from backend.config import GEMINI_CHAT_MODEL
from backend.database import connection_scope
from backend.scripts.build_business_db import slugify
from backend.services import ai_service
from backend.services.chat_markdown_service import normalize_chat_answer_markdown
from backend.services.catalog_service import _filter_visible_article_rows, _serialize_articles
from backend.services.content_localization import contains_cjk
from backend.services.knowledge_profile_service import get_theme_profile, refresh_theme_profile
from backend.services.knowledge_retrieval_service import RetrievalScope, log_answer_event, retrieve_scope_context

DEFAULT_THEME_PAGE_SIZE = 24
MAX_THEME_PAGE_SIZE = 60


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _copy(language: str, zh: str, en: str) -> str:
    return zh if language == "zh" else en


def _normalize_language(requested_language: str | None, text: str = "") -> str:
    normalized = "en" if str(requested_language or "").strip().lower() == "en" else "zh"
    if contains_cjk(text):
        return "zh"
    return normalized


def _normalize_theme_title(value: str | None) -> str:
    title = re.sub(r"\s+", " ", str(value or "").strip())
    if not title:
        raise HTTPException(status_code=400, detail="Theme title is required")
    return title[:80]


def _normalize_description(value: str | None) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:240] if text else None


def _unique_theme_slug(connection, user_id: str, base_slug: str, *, exclude_id: int | None = None) -> str:
    safe_base = (slugify(base_slug) or slugify("knowledge-theme")).strip("-")[:72] or "knowledge-theme"
    candidate = safe_base
    suffix = 2
    while True:
        if exclude_id is None:
            existing = connection.execute(
                "SELECT id FROM user_knowledge_themes WHERE user_id = ? AND slug = ?",
                (user_id, candidate),
            ).fetchone()
        else:
            existing = connection.execute(
                "SELECT id FROM user_knowledge_themes WHERE user_id = ? AND slug = ? AND id != ?",
                (user_id, candidate, exclude_id),
            ).fetchone()
        if existing is None:
            return candidate
        candidate = f"{safe_base[:64]}-{suffix}"
        suffix += 1


def _fetch_theme_row(connection, user_id: str, *, theme_id: int | None = None, slug: str | None = None):
    if theme_id is None and not slug:
        raise ValueError("theme_id or slug is required")
    if theme_id is not None:
        row = connection.execute(
            """
            SELECT id, user_id, slug, title, description, created_at, updated_at
            FROM user_knowledge_themes
            WHERE id = ? AND user_id = ?
            """,
            (theme_id, user_id),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT id, user_id, slug, title, description, created_at, updated_at
            FROM user_knowledge_themes
            WHERE slug = ? AND user_id = ?
            """,
            (slug, user_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Knowledge theme not found")
    return row


def _theme_article_count(connection, theme_id: int) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM user_knowledge_theme_articles WHERE theme_id = ?",
            (theme_id,),
        ).fetchone()[0]
    )


def _theme_article_rows(connection, theme_id: int, *, limit: int, offset: int = 0):
    rows = connection.execute(
        """
        SELECT
            a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
            a.main_topic, a.view_count, a.cover_image_path, a.link
        FROM user_knowledge_theme_articles ukta
        JOIN articles a ON a.id = ukta.article_id
        WHERE ukta.theme_id = ?
        ORDER BY ukta.created_at DESC, a.publish_date DESC, a.id DESC
        LIMIT ? OFFSET ?
        """,
        (theme_id, limit, offset),
    ).fetchall()
    return _filter_visible_article_rows(connection, rows)


def _build_theme_summary_payload(
    connection,
    row,
    *,
    user_id: str,
    membership_profile: dict | None,
    article_id: int | None = None,
    preview_limit: int = 3,
) -> dict:
    theme_id = int(row["id"])
    theme_profile = get_theme_profile(theme_id)
    preview_rows = _theme_article_rows(connection, theme_id, limit=max(0, preview_limit), offset=0)
    preview_articles = _serialize_articles(
        connection,
        preview_rows,
        current_user_id=user_id,
        membership_profile=membership_profile,
    )
    contains_article = False
    if article_id:
        contains_article = (
            connection.execute(
                "SELECT 1 FROM user_knowledge_theme_articles WHERE theme_id = ? AND article_id = ?",
                (theme_id, article_id),
            ).fetchone()
            is not None
        )

    latest_publish_date = theme_profile.get("latest_publish_date")
    if not latest_publish_date and preview_rows:
        latest_publish_date = max(str(item["publish_date"]) for item in preview_rows if item["publish_date"])
    article_count = int(theme_profile.get("article_count") or _theme_article_count(connection, theme_id))

    return {
        "id": theme_id,
        "title": row["title"],
        "slug": row["slug"],
        "description": row["description"],
        "article_count": article_count,
        "contains_article": contains_article,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "latest_publish_date": latest_publish_date,
        "preview_articles": preview_articles,
    }


def _ensure_article_exists(connection, article_id: int):
    row = connection.execute(
        """
        SELECT
            id, title, slug, publish_date, source, excerpt, article_type,
            main_topic, view_count, cover_image_path, link
        FROM articles
        WHERE id = ?
        """,
        (article_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    visible_rows = _filter_visible_article_rows(connection, [row])
    if not visible_rows:
        raise HTTPException(status_code=404, detail="Article not found")
    return row


def list_user_knowledge_themes(
    user_id: str,
    *,
    membership_profile: dict | None = None,
    article_id: int | None = None,
) -> dict:
    with connection_scope() as connection:
        if article_id is not None:
            _ensure_article_exists(connection, article_id)
        rows = connection.execute(
            """
            SELECT id, user_id, slug, title, description, created_at, updated_at
            FROM user_knowledge_themes
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
        items = [
            _build_theme_summary_payload(
                connection,
                row,
                user_id=user_id,
                membership_profile=membership_profile,
                article_id=article_id,
            )
            for row in rows
        ]
    return {"items": items, "total": len(items)}


def create_user_knowledge_theme(
    user_id: str,
    *,
    title: str,
    description: str | None = None,
    membership_profile: dict | None = None,
    initial_article_id: int | None = None,
) -> dict:
    normalized_title = _normalize_theme_title(title)
    normalized_description = _normalize_description(description)
    now = _now_iso()
    with connection_scope() as connection:
        if initial_article_id is not None:
            _ensure_article_exists(connection, initial_article_id)
        unique_slug = _unique_theme_slug(connection, user_id, normalized_title)
        connection.execute(
            """
            INSERT INTO user_knowledge_themes (
                user_id, slug, title, description, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, unique_slug, normalized_title, normalized_description, now, now),
        )
        theme_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        if initial_article_id is not None:
            connection.execute(
                """
                INSERT OR IGNORE INTO user_knowledge_theme_articles (
                    theme_id, article_id, created_at
                )
                VALUES (?, ?, ?)
                """,
                (theme_id, initial_article_id, now),
            )
            connection.execute(
                "UPDATE user_knowledge_themes SET updated_at = ? WHERE id = ?",
                (now, theme_id),
            )
        connection.commit()
        refresh_theme_profile(theme_id)
        row = _fetch_theme_row(connection, user_id, theme_id=theme_id)
        return _build_theme_summary_payload(
            connection,
            row,
            user_id=user_id,
            membership_profile=membership_profile,
            article_id=initial_article_id,
        )


def update_user_knowledge_theme(
    user_id: str,
    theme_slug: str,
    *,
    title: str | None = None,
    description: str | None = None,
    title_provided: bool = False,
    description_provided: bool = False,
    membership_profile: dict | None = None,
) -> dict:
    with connection_scope() as connection:
        current = _fetch_theme_row(connection, user_id, slug=theme_slug)
        next_title = _normalize_theme_title(title) if title_provided else str(current["title"]).strip()
        next_description = _normalize_description(description) if description_provided else current["description"]
        next_slug = _unique_theme_slug(connection, user_id, next_title, exclude_id=int(current["id"]))
        connection.execute(
            """
            UPDATE user_knowledge_themes
            SET slug = ?, title = ?, description = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (next_slug, next_title, next_description, _now_iso(), int(current["id"]), user_id),
        )
        connection.commit()
        refresh_theme_profile(int(current["id"]))
        row = _fetch_theme_row(connection, user_id, theme_id=int(current["id"]))
        return _build_theme_summary_payload(
            connection,
            row,
            user_id=user_id,
            membership_profile=membership_profile,
        )


def delete_user_knowledge_theme(user_id: str, theme_slug: str) -> dict:
    with connection_scope() as connection:
        row = _fetch_theme_row(connection, user_id, slug=theme_slug)
        theme_id = int(row["id"])
        connection.execute("DELETE FROM user_theme_profiles WHERE theme_id = ?", (theme_id,))
        connection.execute("DELETE FROM user_knowledge_theme_articles WHERE theme_id = ?", (theme_id,))
        connection.execute("DELETE FROM user_knowledge_themes WHERE id = ? AND user_id = ?", (theme_id, user_id))
        connection.commit()
    return {"deleted": True, "slug": theme_slug}


def get_user_knowledge_theme_detail(
    user_id: str,
    theme_slug: str,
    *,
    membership_profile: dict | None = None,
    page: int = 1,
    page_size: int = DEFAULT_THEME_PAGE_SIZE,
) -> dict:
    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size), MAX_THEME_PAGE_SIZE))
    offset = (safe_page - 1) * safe_page_size
    with connection_scope() as connection:
        row = _fetch_theme_row(connection, user_id, slug=theme_slug)
        base = _build_theme_summary_payload(
            connection,
            row,
            user_id=user_id,
            membership_profile=membership_profile,
            preview_limit=4,
        )
        article_rows = _theme_article_rows(connection, int(row["id"]), limit=safe_page_size, offset=offset)
        articles = _serialize_articles(
            connection,
            article_rows,
            current_user_id=user_id,
            membership_profile=membership_profile,
        )
        base.update(
            {
                "total": base["article_count"],
                "page": safe_page,
                "page_size": safe_page_size,
                "articles": articles,
            }
        )
        return base


def set_article_in_user_knowledge_theme(
    user_id: str,
    theme_id: int,
    article_id: int,
    *,
    active: bool,
) -> dict:
    now = _now_iso()
    with connection_scope() as connection:
        _fetch_theme_row(connection, user_id, theme_id=theme_id)
        _ensure_article_exists(connection, article_id)
        if active:
            connection.execute(
                """
                INSERT OR IGNORE INTO user_knowledge_theme_articles (
                    theme_id, article_id, created_at
                )
                VALUES (?, ?, ?)
                """,
                (theme_id, article_id, now),
            )
        else:
            connection.execute(
                "DELETE FROM user_knowledge_theme_articles WHERE theme_id = ? AND article_id = ?",
                (theme_id, article_id),
            )
        connection.execute(
            "UPDATE user_knowledge_themes SET updated_at = ? WHERE id = ? AND user_id = ?",
            (now, theme_id, user_id),
        )
        connection.commit()
        profile = refresh_theme_profile(theme_id)
        return {
            "theme_id": theme_id,
            "article_id": article_id,
            "active": active,
            "article_count": int(profile.get("article_count") or 0),
        }


def _theme_allowed_article_ids(connection, theme_id: int) -> list[int]:
    rows = connection.execute(
        "SELECT article_id FROM user_knowledge_theme_articles WHERE theme_id = ? ORDER BY created_at DESC",
        (theme_id,),
    ).fetchall()
    return [int(row["article_id"]) for row in rows]


def _resolve_chat_article_ids(theme_article_ids: list[int], selected_article_ids: list[int] | None) -> list[int]:
    allowed_lookup = {int(article_id) for article_id in theme_article_ids}
    if selected_article_ids is None:
        return [int(article_id) for article_id in theme_article_ids]

    resolved: list[int] = []
    seen: set[int] = set()
    for raw_value in selected_article_ids:
        article_id = int(raw_value)
        if article_id not in allowed_lookup or article_id in seen:
            continue
        resolved.append(article_id)
        seen.add(article_id)
    return resolved


def _fetch_theme_source_rows(connection, article_ids: list[int], *, limit: int = 5) -> list[dict]:
    if not article_ids:
        return []
    limited_ids = [int(value) for value in article_ids[: max(1, limit)]]
    placeholders = ",".join("?" for _ in limited_ids)
    rows = connection.execute(
        f"""
        SELECT
            id, title, slug, publish_date, source, excerpt, article_type, main_topic,
            view_count, cover_image_path, link, content
        FROM articles
        WHERE id IN ({placeholders})
        ORDER BY publish_date DESC, id DESC
        """,
        limited_ids,
    ).fetchall()
    by_id = {int(row["id"]): dict(row) for row in _filter_visible_article_rows(connection, rows)}
    return [by_id[article_id] for article_id in limited_ids if article_id in by_id]


def _build_context_blocks(rows: list[dict]) -> str:
    blocks: list[str] = []
    for index, item in enumerate(rows, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[{index}] Title: {item['title']}",
                    f"Date: {item['publish_date']}",
                    f"Topic: {item.get('main_topic') or 'N/A'}",
                    f"Excerpt: {item.get('excerpt') or ''}",
                    f"Content: {str(item.get('content') or '')[:3600]}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fallback_answer(question: str, theme_title: str, rows: list[dict], language: str) -> str:
    if not rows:
        return _copy(
            language,
            f"主题“{theme_title}”里还没有收录文章，先把文章加入这个知识库主题，再继续提问。",
            f'The theme "{theme_title}" does not contain any articles yet. Add articles to this theme first.',
        )

    intro = _copy(
        language,
        f"我先基于“{theme_title}”里当前最相关的资料给你一版可继续展开的阅读提要：",
        f'Here is a first reading brief from the most relevant materials currently stored in "{theme_title}":',
    )
    lines = [intro, ""]
    for index, item in enumerate(rows[:4], start=1):
        lines.append(f"{index}. **{item['title']}** ({item['publish_date']})")
        excerpt = str(item.get("excerpt") or item.get("main_topic") or "").strip()
        if excerpt:
            lines.append(f"   {excerpt}")
        lines.append("")
    lines.append(
        _copy(
            language,
            f"如果你愿意，我可以继续围绕“{question or theme_title}”做一版简报、总结或者时间线。",
            f'If useful, I can keep going on "{question or theme_title}" with a brief, a synthesis, or a timeline.',
        )
    )
    return "\n".join(lines)


def _no_selection_answer(theme_title: str, language: str) -> str:
    return _copy(
        language,
        f'你还没有为“{theme_title}”选中文章。请先全选，或手动勾选几篇后再继续问 AI。',
        f'No article is selected inside "{theme_title}" yet. Select all or choose a few articles first, then ask AI again.',
    )


def _follow_up_questions(theme_title: str, language: str) -> list[str]:
    subject = theme_title.strip() or _copy(language, "当前主题", "this theme")
    if language == "zh":
        return [
            f"请基于“{subject}”做一份核心简报",
            f"请总结“{subject}”最值得追踪的三条判断",
            f"请按时间线梳理“{subject}”的关键变化",
        ]
    return [
        f"Give me an executive brief for {subject}",
        f"Summarize the three most important judgments in {subject}",
        f"Build a timeline of the key shifts inside {subject}",
    ]


def _build_chat_history(messages: list[dict], *, max_items: int = 4) -> str:
    user_turns = [
        str(message.get("content") or "").strip()
        for message in messages
        if str(message.get("role") or "") == "user" and str(message.get("content") or "").strip()
    ]
    if len(user_turns) <= 1:
        return ""
    previous_questions = user_turns[:-1][-max_items:]
    return "\n".join(f"user: {item}" for item in previous_questions if item)


def chat_with_user_knowledge_theme(
    user_id: str,
    theme_slug: str,
    *,
    messages: list[dict],
    membership_profile: dict | None = None,
    language: str = "zh",
    selected_article_ids: list[int] | None = None,
) -> dict:
    user_messages = [message for message in messages if str(message.get("role") or "") == "user" and str(message.get("content") or "").strip()]
    latest_question = str(user_messages[-1]["content"]).strip() if user_messages else ""
    if not latest_question:
        raise HTTPException(status_code=400, detail="Question is required")

    response_language = _normalize_language(language, latest_question)
    history_text = _build_chat_history(messages)

    with connection_scope() as connection:
        theme_row = _fetch_theme_row(connection, user_id, slug=theme_slug)
        theme_id = int(theme_row["id"])
        theme_title = str(theme_row["title"])
        theme_article_ids = _theme_allowed_article_ids(connection, theme_id)
        if not theme_article_ids:
            return {
                "answer": _fallback_answer(latest_question, theme_title, [], response_language),
                "sources": [],
                "follow_up_questions": _follow_up_questions(theme_title, response_language),
                "confidence": 0.2,
            }

        allowed_article_ids = _resolve_chat_article_ids(theme_article_ids, selected_article_ids)
        if not allowed_article_ids:
            return {
                "answer": _no_selection_answer(theme_title, response_language),
                "sources": [],
                "follow_up_questions": _follow_up_questions(theme_title, response_language),
                "confidence": 0.1,
            }
    retrieval = retrieve_scope_context(
        latest_question,
        scope=RetrievalScope(
            scope_type="selected_articles",
            user_id=user_id,
            theme_id=theme_id,
            article_ids=allowed_article_ids,
        ),
        page_size=5,
        language=response_language,
        membership_profile=membership_profile,
    )
    sources = retrieval["sources"]
    chunk_hits = retrieval["chunk_hits"]

    if ai_service.is_ai_enabled() and chunk_hits:
        try:
            answer = ai_service.answer_with_sources(
                latest_question,
                history_text,
                retrieval["context_blocks"],
                response_language=response_language,
            )
            answer_model = GEMINI_CHAT_MODEL
        except Exception:
            answer = _fallback_answer(latest_question, theme_title, sources, response_language)
            answer_model = "fallback"
    else:
        answer = _fallback_answer(latest_question, theme_title, sources, response_language)
        answer_model = "fallback"

    log_answer_event(
        user_id=user_id,
        scope=RetrievalScope(
            scope_type="selected_articles",
            user_id=user_id,
            theme_id=theme_id,
            article_ids=allowed_article_ids,
        ),
        question=latest_question,
        answer_model=answer_model,
        selected_article_count=len(allowed_article_ids),
        source_article_count=len(sources),
        source_chunk_count=len(chunk_hits),
        metadata={"language": response_language, "theme_slug": theme_slug},
    )
    confidence = min(1.0, (sources[0]["score"] / 12) if sources and sources[0].get("score") else 0.45)
    return {
        "answer": normalize_chat_answer_markdown(answer),
        "sources": sources,
        "follow_up_questions": _follow_up_questions(theme_title, response_language),
        "confidence": round(confidence, 2),
    }
