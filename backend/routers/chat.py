from __future__ import annotations

import re
import uuid

from fastapi import APIRouter

from backend.models.schemas import ChatRequest, ChatResponse, ChatSessionDeleteResponse, ChatSessionDetail, ChatSessionSummary
from backend.services import ai_service, rag_engine
from backend.services.chat_markdown_service import normalize_chat_answer_markdown
from backend.services.catalog_service import (
    append_chat_message,
    delete_chat_session,
    get_daily_read,
    get_chat_session_detail,
    get_recommended_articles,
    list_chat_sessions,
    store_chat_session,
)
from backend.services.content_localization import contains_cjk
from backend.services.knowledge_retrieval_service import RetrievalScope, retrieve_scope_context

router = APIRouter(prefix="/api", tags=["chat"])

COMPARE_SPLIT_PATTERN = re.compile(r"\s+(?:vs\.?|versus|\u4e0e|\u548c)\s+", re.IGNORECASE)
COMMAND_ALIASES = {
    "/brief": "/brief",
    "/summarize": "/summarize",
    "/compare": "/compare",
    "/timeline": "/timeline",
    "/today": "/today",
    "/recommend": "/recommend",
    "/\u7b80\u62a5": "/brief",
    "/\u603b\u7ed3": "/summarize",
    "/\u6458\u8981": "/summarize",
    "/\u6bd4\u8f83": "/compare",
    "/\u5bf9\u6bd4": "/compare",
    "/\u65f6\u95f4\u7ebf": "/timeline",
    "/\u8109\u7edc": "/timeline",
    "/\u4eca\u65e5\u4e00\u8bfb": "/today",
    "/\u4e00\u8bfb": "/today",
    "/\u4eca\u65e5": "/today",
    "/\u4eca\u5929": "/today",
    "/\u4eca\u65e5\u7b80\u62a5": "/today",
    "/\u7ee7\u7eed\u9605\u8bfb": "/recommend",
    "/\u5ef6\u4f38\u9605\u8bfb": "/recommend",
    "/\u63a8\u8350": "/recommend",
}


def _copy(language: str, zh: str, en: str) -> str:
    return zh if language == "zh" else en


def _normalize_language(requested_language: str | None, text: str = "") -> str:
    normalized = "en" if str(requested_language or "").strip().lower() == "en" else "zh"
    if contains_cjk(text):
        return "zh"
    return normalized


def _build_article_context_blocks(sources: list[dict]) -> str:
    blocks = []
    for index, item in enumerate(sources, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[{index}] Title: {item['title']}",
                    f"Date: {item['publish_date']}",
                    f"Topic: {item.get('main_topic') or 'N/A'}",
                    f"Excerpt: {item.get('excerpt') or ''}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _build_chunk_context_blocks(chunk_hits: list[dict], limit: int = 6) -> str:
    blocks: list[str] = []
    for index, item in enumerate(chunk_hits[: max(limit, 1)], start=1):
        blocks.append(
            "\n".join(
                [
                    f"[{index}] Title: {item['title']}",
                    f"Date: {item['publish_date']}",
                    f"Heading: {item.get('heading') or item['title']}",
                    f"Excerpt: {item.get('excerpt') or ''}",
                    f"Chunk: {str(item.get('content') or '')[:1800]}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fallback_answer(question: str, sources: list[dict], language: str) -> str:
    if not sources:
        return _copy(
            language,
            f"\u5f53\u524d\u77e5\u8bc6\u5e93\u91cc\u6682\u65f6\u6ca1\u6709\u627e\u5230\u8db3\u591f\u76f8\u5173\u7684\u4e1a\u52a1\u6750\u6599\u3002\u5efa\u8bae\u6362\u4e00\u4e2a\u66f4\u5177\u4f53\u7684\u4e3b\u9898\u7ee7\u7eed\u95ee\u201c{question}\u201d\u3002",
            f'The knowledge base does not yet have enough relevant material for "{question}". Try a more specific topic or angle.',
        )

    intro = _copy(
        language,
        "\u57fa\u4e8e\u5f53\u524d\u68c0\u7d22\u5230\u7684\u6750\u6599\uff0c\u53ef\u4ee5\u5148\u4ece\u4e0b\u5217\u9605\u8bfb\u8def\u5f84\u5165\u624b\uff1a",
        "Based on the currently matched materials, start with these reading paths:",
    )
    lines = [intro, ""]
    for index, item in enumerate(sources[:4], start=1):
        lines.append(f"{index}. **{item['title']}** ({item['publish_date']})")
        if item.get("excerpt"):
            lines.append(f"   {item['excerpt']}")
        lines.append("")
    lines.append(
        _copy(
            language,
            f"\u5982\u679c\u4f60\u613f\u610f\uff0c\u6211\u53ef\u4ee5\u56f4\u7ed5\u201c{question}\u201d\u7ee7\u7eed\u505a\u6218\u7565\u7b80\u62a5\u3001\u65f6\u95f4\u7ebf\u6216\u5dee\u5f02\u6bd4\u8f83\u3002",
            f'If useful, I can keep working on "{question}" as an executive brief, a timeline, or a comparison next.',
        )
    )
    return "\n".join(lines)


def _public_retrieval(
    query: str,
    *,
    language: str,
    page_size: int,
    source_limit: int | None = None,
    sort: str = "relevance",
) -> dict:
    retrieval = retrieve_scope_context(
        query,
        scope=RetrievalScope(scope_type="global_public"),
        page_size=page_size,
        source_limit=source_limit,
        language=language,
    )
    if retrieval["sources"]:
        if sort == "date":
            sorted_sources = sorted(
                retrieval["sources"],
                key=lambda item: (str(item.get("publish_date") or ""), float(item.get("score") or 0.0)),
                reverse=True,
            )
            sorted_chunks = sorted(
                retrieval["chunk_hits"],
                key=lambda item: (str(item.get("publish_date") or ""), float(item.get("score") or 0.0)),
                reverse=True,
            )
            retrieval = {
                **retrieval,
                "sources": sorted_sources,
                "chunk_hits": sorted_chunks,
                "context_blocks": _build_chunk_context_blocks(sorted_chunks),
            }
        return retrieval

    search_payload = rag_engine.search_articles(
        query,
        mode="smart",
        sort=sort,
        page=1,
        page_size=page_size,
        language=language,
    )
    return {
        "sources": search_payload["items"],
        "chunk_hits": [],
        "context_blocks": _build_article_context_blocks(search_payload["items"]),
        "total_sources": search_payload.get("total", 0),
        "total_chunks": 0,
        "provider": "legacy_search_fallback",
    }


def _answer_from_context(
    question: str,
    history_text: str,
    context_blocks: str,
    sources: list[dict],
    fallback_question: str,
    language: str,
) -> str:
    if ai_service.is_ai_enabled() and sources and str(context_blocks or "").strip():
        try:
            return ai_service.answer_with_sources(
                question,
                history_text,
                context_blocks,
                response_language=language,
            )
        except Exception:
            return _fallback_answer(fallback_question, sources, language)
    return _fallback_answer(fallback_question, sources, language)


def _dedupe_sources(*groups: list[dict]) -> list[dict]:
    items: list[dict] = []
    seen: set[int] = set()
    for group in groups:
        for item in group:
            article_id = item["id"]
            if article_id not in seen:
                seen.add(article_id)
                items.append(item)
    return items


def _canonical_command_label(command: str, language: str) -> str:
    labels = {
        "/brief": _copy(language, "/\u7b80\u62a5", "/brief"),
        "/summarize": _copy(language, "/\u603b\u7ed3", "/summarize"),
        "/compare": _copy(language, "/\u6bd4\u8f83", "/compare"),
        "/timeline": _copy(language, "/\u65f6\u95f4\u7ebf", "/timeline"),
        "/today": _copy(language, "/\u4eca\u65e5\u4e00\u8bfb", "/today"),
        "/recommend": _copy(language, "/\u7ee7\u7eed\u9605\u8bfb", "/recommend"),
    }
    return labels.get(command, command)


def _format_command(command: str, argument: str, language: str) -> str:
    base = _canonical_command_label(command, language)
    cleaned_argument = str(argument or "").strip()
    return f"{base} {cleaned_argument}".strip()


def _command_usage(command: str, language: str, usage_zh: str, usage_en: str) -> dict:
    usage = usage_zh if language == "zh" else usage_en
    display_command = _canonical_command_label(command, language)
    return {
        "answer": _copy(
            language,
            f"\u6307\u4ee4\u683c\u5f0f\u4e0d\u5b8c\u6574\uff0c\u8bf7\u4f7f\u7528\uff1a`{usage}`",
            f"The command format is incomplete. Use `{usage}`.",
        ),
        "sources": [],
        "follow_up_questions": [usage, _format_command("/today", "", language), _format_command("/recommend", "", language)],
        "confidence": 0.2,
        "title": display_command,
    }


def _trim_display_text(text: str | None, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value or len(value) <= limit:
        return value
    clipped = value[:limit].rstrip(",;:!?-\u3002\uff0c\uff1b\uff1a\uff01\uff1f")
    if " " in clipped and not contains_cjk(clipped):
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped + "..."


def _first_topic(sources: list[dict], fallback: str = "") -> str:
    for item in sources:
        topic = str(item.get("main_topic") or "").strip()
        if topic:
            return topic
    return str(fallback or "").strip()


def _compact_follow_up_subject(primary: str, fallback: str, language: str) -> str:
    candidate = re.sub(r"\s+", " ", str(primary or fallback or "").strip())
    if not candidate:
        return ""

    if language == "en":
        candidate = re.split(r"[.!?;:]", candidate, maxsplit=1)[0].strip()
        if len(candidate) > 44:
            clipped = candidate[:44]
            candidate = clipped.rsplit(" ", 1)[0].strip() if " " in clipped else clipped.strip()
    else:
        candidate = re.split(r"[\u3002\uff0c\uff1b\uff1a\uff01\uff1f]", candidate, maxsplit=1)[0].strip()
        if len(candidate) > 16:
            candidate = candidate[:16].strip()

    if candidate:
        return candidate
    return re.sub(r"\s+", " ", str(fallback or "").strip())


def _default_brief_subject(language: str) -> str:
    return "AI strategy" if language == "en" else "\u4eba\u5de5\u667a\u80fd\u6218\u7565"


def _default_timeline_subject(language: str) -> str:
    return "Generative AI" if language == "en" else "\u751f\u6210\u5f0fAI"


def _build_command_follow_ups(topic: str, language: str) -> list[str]:
    subject = _compact_follow_up_subject(topic, _default_brief_subject(language), language)
    return [
        _format_command("/brief", subject or _default_brief_subject(language), language),
        _format_command("/timeline", subject or _default_timeline_subject(language), language),
        _format_command("/recommend", subject or _default_brief_subject(language), language),
    ]


def _parse_iso_date_argument(argument: str) -> str | None:
    cleaned = str(argument or "").strip()
    if not cleaned:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return cleaned
    return ""


def _build_daily_read_answer(item: dict, language: str) -> str:
    main_topic = _trim_display_text(item.get("main_topic") or "", 42 if language == "zh" else 72)
    excerpt = _trim_display_text(item.get("excerpt") or "", 140 if language == "zh" else 220)
    selection_note = _copy(
        language,
        f"\u7cfb\u7edf\u6309 {item['generated_at']} ({item['timezone']}) \u8ba1\u7b97\u5f53\u524d\u65f6\u95f4\uff0c\u5e76\u5c06 {item['reading_date']} \u4f5c\u4e3a\u9605\u8bfb\u65e5\uff0c\u4ece\u8fd1 {item['selection_window_days']} \u5929\u7684\u9ad8\u4ef7\u503c\u6587\u7ae0\u4e2d\u8f6e\u6362\u9009\u51fa\u4e00\u7bc7\u3002\u5b83\u662f\u201c\u4eca\u65e5\u4e00\u8bfb\u201d\uff0c\u4e0d\u662f\u5f53\u65e5\u65b0\u95fb\u5feb\u62a5\u3002",
        f"The system computes the current local time as {item['generated_at']} ({item['timezone']}) and uses {item['reading_date']} as the reading date. It rotates one pick from the past {item['selection_window_days']} days of high-signal articles. This is a daily read, not a breaking-news brief.",
    )
    topic_line = (
        _copy(language, f"**\u4e3b\u7ebf**\uff1a{main_topic}", f"**Focus**: {main_topic}")
        if main_topic
        else _copy(language, "**\u4e3b\u7ebf**\uff1a\u4ece\u6b64\u7bc7\u5f00\u59cb\u5ef6\u4f38\u9605\u8bfb", "**Focus**: Start your next reading path from this article")
    )
    summary_block = excerpt or _copy(language, "\u53ef\u4ece\u539f\u6587\u8fdb\u4e00\u6b65\u6df1\u5165\u9605\u8bfb\u3002", "Open the source article to continue reading in depth.")
    return _copy(
        language,
        f"## \u4eca\u65e5\u4e00\u8bfb | {item['reading_date']}\n\n**{item['title']}**\uff08\u53d1\u5e03\u4e8e {item['publish_date']}\uff09\n\n> {item['quote']}\n\n{topic_line}\n\n{selection_note}\n\n{summary_block}",
        f"## Today Read | {item['reading_date']}\n\n**{item['title']}** (Published on {item['publish_date']})\n\n> {item['quote']}\n\n{topic_line}\n\n{selection_note}\n\n{summary_block}",
    )


def _build_continue_reading_answer(items: list[dict], mode: str, language: str, subject: str = "") -> str:
    if not items:
        return _copy(
            language,
            "\u5f53\u524d\u8fd8\u6ca1\u6709\u8db3\u591f\u53ef\u7528\u7684\u5ef6\u4f38\u9605\u8bfb\u7ebf\u7d22\uff0c\u5efa\u8bae\u5148\u6362\u4e00\u4e2a\u66f4\u5177\u4f53\u7684\u4e3b\u9898\u6216\u5148\u5b8c\u6210\u4e00\u8f6e\u63d0\u95ee\u3002",
            "There is not enough material yet for a solid next-reading path. Try a more specific topic or ask one focused question first.",
        )

    if subject:
        intro = _copy(
            language,
            f"\u56f4\u7ed5\u201c{subject}\u201d\uff0c\u5efa\u8bae\u4f60\u7ee7\u7eed\u8bfb\u8fd9\u51e0\u7bc7\uff1a",
            f'Continue reading around "{subject}" with these picks:',
        )
    elif mode == "contextual":
        intro = _copy(
            language,
            "\u57fa\u4e8e\u4f60\u8fd9\u8f6e\u5bf9\u8bdd\u5df2\u7ecf\u6d89\u53ca\u7684\u5185\u5bb9\uff0c\u5efa\u8bae\u7ee7\u7eed\u5f80\u4e0b\u8bfb\uff1a",
            "Based on what this conversation has already touched, these are the best next reads:",
        )
    else:
        intro = _copy(
            language,
            "\u5f53\u524d\u4f1a\u8bdd\u8fd8\u6ca1\u6709\u8db3\u591f\u4e0a\u4e0b\u6587\uff0c\u5148\u7ed9\u4f60\u4e00\u7ec4\u7ad9\u5185\u9ad8\u4ef7\u503c\u9605\u8bfb\uff1a",
            "There is not enough session context yet, so here is a high-signal reading list from the knowledge base:",
        )

    lines = [f"## {_copy(language, '\u7ee7\u7eed\u9605\u8bfb', 'Continue Reading')}", "", intro, ""]
    for index, item in enumerate(items[:5], start=1):
        why_read = _trim_display_text(item.get("main_topic") or item.get("excerpt") or "", 88 if language == "zh" else 140)
        excerpt = _trim_display_text(item.get("excerpt") or "", 120 if language == "zh" else 180)
        lines.append(f"{index}. **{item['title']}** ({item['publish_date']})")
        if why_read:
            lines.append(f"   {_copy(language, '\u4e3a\u4ec0\u4e48\u8bfb', 'Why read')}\uff1a{why_read}")
        if excerpt and excerpt != why_read:
            lines.append(f"   {excerpt}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_follow_ups(question: str, sources: list[dict], language: str) -> list[str]:
    topic = _compact_follow_up_subject(_first_topic(sources, question), question, language)
    if not topic:
        return [
            _format_command("/brief", _default_brief_subject(language), language),
            _format_command("/today", "", language),
            _format_command("/recommend", "", language),
        ]
    return _build_command_follow_ups(topic, language)


def _parse_command(command_text: str) -> tuple[str, str] | None:
    stripped = command_text.strip()
    if not stripped.startswith("/"):
        return None
    command_token, _, raw_argument = stripped.partition(" ")
    canonical_command = COMMAND_ALIASES.get(command_token.lower(), command_token.lower())
    return canonical_command, raw_argument.strip()


def _dispatch_command(command_text: str, history_text: str, session_id: str | None, language: str) -> dict | None:
    parsed = _parse_command(command_text)
    if parsed is None:
        return None

    command, argument = parsed

    if command == "/brief":
        if not argument:
            return _command_usage(command, language, "/\u7b80\u62a5 [\u4e3b\u9898]", "/brief [topic]")
        retrieval = _public_retrieval(argument, language=language, page_size=6)
        sources = retrieval["sources"]
        answer = _answer_from_context(
            f"Create an executive brief on '{argument}'. Cover the core signals, business implications, what deserves immediate attention, and the next questions worth tracking.",
            history_text,
            retrieval["context_blocks"],
            sources,
            argument,
            language,
        )
        return {
            "answer": answer,
            "sources": sources,
            "follow_up_questions": [
                _format_command("/timeline", argument, language),
                _format_command("/summarize", argument, language),
                _format_command("/recommend", argument, language),
            ],
            "confidence": 0.88 if sources else 0.3,
            "title": _format_command(command, argument, language),
        }

    if command == "/summarize":
        if not argument:
            return _command_usage(command, language, "/\u603b\u7ed3 [\u4e3b\u9898]", "/summarize [topic]")
        retrieval = _public_retrieval(argument, language=language, page_size=6)
        sources = retrieval["sources"]
        answer = _answer_from_context(
            f"Summarize the core viewpoints, representative themes, and open questions around '{argument}'. Keep the answer dense and source-grounded.",
            history_text,
            retrieval["context_blocks"],
            sources,
            argument,
            language,
        )
        return {
            "answer": answer,
            "sources": sources,
            "follow_up_questions": [
                _format_command("/brief", argument, language),
                _format_command("/timeline", argument, language),
                _format_command("/recommend", argument, language),
            ],
            "confidence": 0.85 if sources else 0.3,
            "title": _format_command(command, argument, language),
        }

    if command == "/timeline":
        if not argument:
            return _command_usage(command, language, "/\u65f6\u95f4\u7ebf [\u4e3b\u9898]", "/timeline [topic]")
        retrieval = _public_retrieval(argument, language=language, page_size=8, sort="date")
        sources = retrieval["sources"]
        answer = _answer_from_context(
            f"Explain the evolution of '{argument}' as a timeline. Highlight key dates, turning points, and how the framing changed over time.",
            history_text,
            retrieval["context_blocks"],
            sources,
            argument,
            language,
        )
        return {
            "answer": answer,
            "sources": sources,
            "follow_up_questions": [
                _format_command("/brief", argument, language),
                _format_command("/summarize", argument, language),
                _format_command("/recommend", argument, language),
            ],
            "confidence": 0.83 if sources else 0.3,
            "title": _format_command(command, argument, language),
        }

    if command == "/compare":
        if not argument:
            return _command_usage(command, language, "/\u6bd4\u8f83 [A] \u4e0e [B]", "/compare [A] vs [B]")
        parts = [item.strip() for item in COMPARE_SPLIT_PATTERN.split(argument) if item.strip()]
        if len(parts) != 2:
            return _command_usage(command, language, "/\u6bd4\u8f83 [A] \u4e0e [B]", "/compare [A] vs [B]")
        left, right = parts
        left_retrieval = _public_retrieval(left, language=language, page_size=4)
        right_retrieval = _public_retrieval(right, language=language, page_size=4)
        left_sources = left_retrieval["sources"]
        right_sources = right_retrieval["sources"]
        sources = _dedupe_sources(left_sources, right_sources)
        merged_context = "\n\n".join(
            block for block in (left_retrieval["context_blocks"], right_retrieval["context_blocks"]) if block
        )
        answer = _answer_from_context(
            f"Compare '{left}' and '{right}'. Show the overlap, the major differences, and what a business reader should read next.",
            history_text,
            merged_context,
            sources,
            f"{left} vs {right}",
            language,
        )
        return {
            "answer": answer,
            "sources": sources,
            "follow_up_questions": [
                _format_command("/timeline", left, language),
                _format_command("/timeline", right, language),
                _format_command("/brief", left, language),
            ],
            "confidence": 0.84 if sources else 0.3,
            "title": _format_command(command, f"{left} {_copy(language, '\u4e0e', 'vs')} {right}", language),
        }

    if command == "/today":
        target_date = _parse_iso_date_argument(argument)
        if target_date == "":
            return _command_usage(command, language, "/\u4eca\u65e5\u4e00\u8bfb [YYYY-MM-DD]", "/today [YYYY-MM-DD]")
        item = get_daily_read(target_date, language=language)
        sources = [item]
        answer = _build_daily_read_answer(item, language)
        topic = _compact_follow_up_subject(item.get("main_topic") or "", item["title"], language)
        return {
            "answer": answer,
            "sources": sources,
            "follow_up_questions": _build_command_follow_ups(topic, language),
            "confidence": 0.88 if sources else 0.45,
            "title": _format_command(command, target_date or "", language),
        }

    if command == "/recommend":
        if argument:
            retrieval = _public_retrieval(argument, language=language, page_size=5)
            sources = retrieval["sources"]
            recommendation_mode = "topic"
        else:
            recommendation_payload = get_recommended_articles(session_id, limit=5, language=language)
            sources = recommendation_payload["items"]
            recommendation_mode = recommendation_payload["mode"]
        answer = _build_continue_reading_answer(sources, recommendation_mode, language, subject=argument)
        topic = _compact_follow_up_subject(_first_topic(sources, argument), argument, language)
        return {
            "answer": answer,
            "sources": sources,
            "follow_up_questions": [
                _format_command("/today", "", language),
                _format_command("/brief", topic or _default_brief_subject(language), language),
                _format_command("/timeline", topic or _default_timeline_subject(language), language),
            ],
            "confidence": 0.8 if sources else 0.35,
            "title": _format_command(command, argument, language),
        }

    return {
        "answer": _copy(
            language,
            "\u6682\u4e0d\u652f\u6301\u8be5\u6307\u4ee4\u3002\u53ef\u7528\u6307\u4ee4\uff1a`/\u7b80\u62a5`\u3001`/\u603b\u7ed3`\u3001`/\u6bd4\u8f83`\u3001`/\u65f6\u95f4\u7ebf`\u3001`/\u4eca\u65e5\u4e00\u8bfb`\u3001`/\u7ee7\u7eed\u9605\u8bfb`\u3002",
            "That shortcut is not supported yet. Available commands: `/brief`, `/summarize`, `/compare`, `/timeline`, `/today`, `/recommend`.",
        ),
        "sources": [],
        "follow_up_questions": [
            _format_command("/brief", _default_brief_subject(language), language),
            _format_command("/today", "", language),
            _format_command("/recommend", "", language),
        ],
        "confidence": 0.2,
        "title": _format_command(command, argument, language),
    }


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    user_messages = [message for message in request.messages if message.role == "user" and message.content.strip()]
    latest_question = user_messages[-1].content.strip() if user_messages else ""
    response_language = _normalize_language(request.language, latest_question)
    session_id = request.session_id or uuid.uuid4().hex
    history_lines = [f"{message.role}: {message.content}" for message in request.messages[-6:]]
    history_text = "\n".join(history_lines)

    command_payload = _dispatch_command(latest_question, history_text, session_id, response_language)
    if command_payload is not None:
        answer = command_payload["answer"]
        sources = command_payload["sources"]
        follow_up_questions = command_payload["follow_up_questions"]
        confidence = command_payload["confidence"]
    else:
        retrieval = _public_retrieval(
            latest_question,
            language=response_language,
            page_size=5,
        )
        sources = retrieval["sources"]
        answer = _answer_from_context(
            latest_question,
            history_text,
            retrieval["context_blocks"],
            sources,
            latest_question,
            response_language,
        )
        follow_up_questions = _build_follow_ups(latest_question, sources, response_language)
        confidence = min(1.0, (sources[0]["score"] / 12) if sources and sources[0].get("score") else 0.45)

    answer = normalize_chat_answer_markdown(answer)
    default_title = _copy(response_language, "\u65b0\u4f1a\u8bdd", "New session")
    title = latest_question[:40] or default_title
    store_chat_session(session_id, title, latest_question)
    if latest_question:
        append_chat_message(session_id, "user", latest_question)
    append_chat_message(session_id, "assistant", answer, sources, follow_up_questions)

    return {
        "session_id": session_id,
        "answer": answer,
        "sources": sources,
        "follow_up_questions": follow_up_questions[:3],
        "confidence": round(confidence, 2),
    }


@router.get("/chat/sessions", response_model=list[ChatSessionSummary])
def chat_sessions():
    return list_chat_sessions()


@router.get("/chat/session/{session_id}", response_model=ChatSessionDetail)
def chat_session_detail(session_id: str):
    return get_chat_session_detail(session_id)


@router.delete("/chat/session/{session_id}", response_model=ChatSessionDeleteResponse)
def chat_session_delete(session_id: str):
    return delete_chat_session(session_id)
