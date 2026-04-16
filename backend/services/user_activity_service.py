from __future__ import annotations

from fastapi import HTTPException

from backend.config import GEMINI_CHAT_MODEL
from backend.database import connection_scope
from backend.services import ai_service
from backend.services.catalog_service import _serialize_articles
from backend.services.chat_markdown_service import normalize_chat_answer_markdown
from backend.services.content_localization import contains_cjk
from backend.services.knowledge_profile_service import get_user_library_profile
from backend.services.knowledge_retrieval_service import RetrievalScope, log_answer_event, retrieve_scope_context


def _fetch_saved_articles(user_id: str, limit: int):
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM user_saved_articles usa
            JOIN articles a ON a.id = usa.article_id
            WHERE usa.user_id = ? AND usa.is_active = 1
            ORDER BY usa.updated_at DESC, usa.article_id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return _serialize_articles(connection, rows, current_user_id=user_id)


def _fetch_articles_for_reaction(user_id: str, reaction_type: str, limit: int):
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link
            FROM article_reactions ar
            JOIN articles a ON a.id = ar.article_id
            WHERE ar.user_id = ? AND ar.reaction_type = ? AND ar.is_active = 1
            ORDER BY ar.updated_at DESC, ar.id DESC
            LIMIT ?
            """,
            (user_id, reaction_type, limit),
        ).fetchall()
        return _serialize_articles(connection, rows, current_user_id=user_id)


def _fetch_recent_views(user_id: str, limit: int):
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                a.id, a.title, a.slug, a.publish_date, a.source, a.excerpt, a.article_type,
                a.main_topic, a.view_count, a.cover_image_path, a.link,
                MAX(ave.created_at) AS last_viewed_at
            FROM article_view_events ave
            JOIN articles a ON a.id = ave.article_id
            WHERE ave.user_id = ?
            GROUP BY a.id
            ORDER BY last_viewed_at DESC, a.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return _serialize_articles(connection, rows, current_user_id=user_id)


def get_user_library(user_id: str, limit: int = 12) -> dict:
    safe_limit = max(1, min(limit, 30))
    profile = get_user_library_profile(user_id)
    return {
        "bookmarks": _fetch_saved_articles(user_id, safe_limit),
        "likes": _fetch_articles_for_reaction(user_id, "like", safe_limit),
        "recent_views": _fetch_recent_views(user_id, safe_limit),
        "saved_count": int(profile.get("saved_count") or 0),
        "latest_saved_at": profile.get("latest_saved_at"),
        "profile_summary": profile.get("summary_text"),
        "top_topics": list(profile.get("top_topics") or []),
        "top_tags": list(profile.get("top_tags") or []),
    }


def _copy(language: str, zh: str, en: str) -> str:
    return zh if language == "zh" else en


def _normalize_language(requested_language: str | None, text: str = "") -> str:
    normalized = "en" if str(requested_language or "").strip().lower() == "en" else "zh"
    return "zh" if contains_cjk(text) else normalized


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


def _library_follow_up_questions(language: str) -> list[str]:
    if language == "zh":
        return [
            "请基于我的资料库生成一份核心简报",
            "请总结这些收藏里最值得追踪的三条判断变化",
            "请按时间线梳理我最近收藏材料的关键进展",
        ]
    return [
        "Build an executive brief from my saved library",
        "Summarize the three most important judgment shifts in these saved articles",
        "Arrange the key developments in my saved articles as a timeline",
    ]


def _library_empty_answer(language: str) -> str:
    return _copy(
        language,
        "你的资料库里还没有正式收藏的文章。先收藏几篇文章，再继续和 AI 讨论。",
        "Your library does not contain any saved articles yet. Save a few articles first, then continue.",
    )


def _library_fallback_answer(question: str, sources: list[dict], language: str) -> str:
    if not sources:
        return _library_empty_answer(language)
    intro = _copy(
        language,
        "我先基于你当前资料库里最相关的收藏，给你一版可继续展开的阅读提要：",
        "Here is a first reading brief from the most relevant items in your saved library:",
    )
    lines = [intro, ""]
    for index, item in enumerate(sources[:4], start=1):
        lines.append(f"{index}. **{item['title']}** ({item['publish_date']})")
        excerpt = str(item.get("excerpt") or item.get("main_topic") or "").strip()
        if excerpt:
            lines.append(f"   {excerpt}")
        lines.append("")
    lines.append(
        _copy(
            language,
            f"如果需要，我可以继续围绕“{question or '当前资料库'}”做简报、比较或时间线。",
            f'If useful, I can continue on "{question or "your library"}" with a brief, comparison, or timeline.',
        )
    )
    return "\n".join(lines)


def chat_with_user_library(
    user_id: str,
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
    scope = RetrievalScope(scope_type="my_library", user_id=user_id, article_ids=selected_article_ids)
    retrieval = retrieve_scope_context(
        latest_question,
        scope=scope,
        page_size=5,
        language=response_language,
        membership_profile=membership_profile,
    )
    sources = retrieval["sources"]
    chunk_hits = retrieval["chunk_hits"]
    if not retrieval["selected_article_ids"]:
        return {
            "answer": _library_empty_answer(response_language),
            "sources": [],
            "follow_up_questions": _library_follow_up_questions(response_language),
            "confidence": 0.1,
        }

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
            answer = _library_fallback_answer(latest_question, sources, response_language)
            answer_model = "fallback"
    else:
        answer = _library_fallback_answer(latest_question, sources, response_language)
        answer_model = "fallback"

    log_answer_event(
        user_id=user_id,
        scope=scope,
        question=latest_question,
        answer_model=answer_model,
        selected_article_count=len(retrieval["selected_article_ids"]),
        source_article_count=len(sources),
        source_chunk_count=len(chunk_hits),
        metadata={"language": response_language},
    )
    confidence = min(1.0, (sources[0]["score"] / 12) if sources and sources[0].get("score") else 0.45)
    return {
        "answer": normalize_chat_answer_markdown(answer),
        "sources": sources,
        "follow_up_questions": _library_follow_up_questions(response_language),
        "confidence": round(confidence, 2),
    }
