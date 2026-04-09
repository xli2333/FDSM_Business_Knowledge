from __future__ import annotations

import itertools
import json
import re
import time
from functools import lru_cache

import requests
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import (
    GEMINI_API_KEYS,
    GEMINI_CHAT_MODEL,
    GEMINI_EDITORIAL_FORMAT_MODEL,
    GEMINI_FLASH_MODEL,
    PRIMARY_GEMINI_KEY,
    resolve_gemini_model_name,
)

_GEMINI_TIMEOUT = (10, 90)
_GEMINI_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_gemini_request_counter = itertools.count()

LAYOUT_MODE_GUIDANCE = {
    "auto": "Default to a polished WeChat-style long-form layout with a short lead, clear H2/H3 hierarchy, and dense but readable information blocks.",
    "insight": "Favor deeper analysis, explicit argument structure, section transitions, and slightly longer analytical paragraphs.",
    "briefing": "Favor rapid scanning with short sections, bullet lists, key takeaways, and compact summaries.",
    "interview": "Preserve speaker turns and Q&A logic while adding a stronger title, lead, and readable section breaks.",
}


@lru_cache(maxsize=1)
def get_gemini_api_keys() -> tuple[str, ...]:
    keys: list[str] = []
    for key in (PRIMARY_GEMINI_KEY, *GEMINI_API_KEYS):
        cleaned = str(key or "").strip()
        if cleaned and cleaned not in keys:
            keys.append(cleaned)
    return tuple(keys)


def is_ai_enabled() -> bool:
    return bool(get_gemini_api_keys())


def _build_llm(model_name: str) -> ChatGoogleGenerativeAI | None:
    keys = get_gemini_api_keys()
    if not keys:
        return None
    return ChatGoogleGenerativeAI(
        model=resolve_gemini_model_name(model_name),
        google_api_key=keys[0],
        temperature=0.2,
        convert_system_message_to_human=True,
    )


@lru_cache(maxsize=1)
def get_llm() -> ChatGoogleGenerativeAI | None:
    return _build_llm(GEMINI_CHAT_MODEL)


@lru_cache(maxsize=1)
def get_flash_llm() -> ChatGoogleGenerativeAI | None:
    return _build_llm(GEMINI_FLASH_MODEL)


def _invoke_prompt(template: str, payload: dict[str, str], *, llm: ChatGoogleGenerativeAI | None = None) -> str:
    model = llm or get_llm()
    if model is None:
        raise RuntimeError("Gemini is not configured.")
    chain = PromptTemplate.from_template(template) | model | StrOutputParser()
    return chain.invoke(payload).strip()


def _strip_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_json_payload(raw: str):
    text = _strip_code_fence(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        first_array = text.find("[")
        last_array = text.rfind("]")
        if first_array != -1 and last_array != -1 and last_array > first_array:
            return json.loads(text[first_array : last_array + 1])
        first_object = text.find("{")
        last_object = text.rfind("}")
        if first_object != -1 and last_object != -1 and last_object > first_object:
            return json.loads(text[first_object : last_object + 1])
        raise


def _extract_gemini_text(response_payload: dict) -> str:
    candidates = response_payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")
    parts = candidates[0].get("content", {}).get("parts") or []
    if not parts:
        raise RuntimeError("Gemini returned no content parts.")
    collected: list[str] = []
    for part in parts:
        text = str(part.get("text") or "").strip()
        if text:
            collected.append(text)
    if not collected:
        raise RuntimeError("Gemini returned an empty body.")
    return "\n".join(collected).strip()


def _request_gemini_text(
    *,
    prompt: str,
    model_name: str,
    response_mime_type: str = "text/plain",
) -> str:
    api_keys = list(get_gemini_api_keys())
    if not api_keys:
        raise RuntimeError("Gemini is not configured.")

    session = requests.Session()
    last_error: Exception | None = None
    start_offset = next(_gemini_request_counter)
    max_attempts = max(3, len(api_keys) * 2)

    for attempt in range(max_attempts):
        api_key = api_keys[(start_offset + attempt) % len(api_keys)]
        runtime_model_name = resolve_gemini_model_name(model_name)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{runtime_model_name}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.25,
                "responseMimeType": response_mime_type,
            },
        }
        try:
            response = session.post(url, json=payload, timeout=_GEMINI_TIMEOUT)
            if response.status_code == 200:
                return _extract_gemini_text(response.json())
            if response.status_code in _GEMINI_RETRYABLE_STATUS:
                last_error = RuntimeError(f"Gemini API error {response.status_code}: {response.text}")
                time.sleep(min(4.0, 0.6 * (attempt + 1)))
                continue
            raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(4.0, 0.6 * (attempt + 1)))
            continue

    raise RuntimeError(f"Gemini request failed: {last_error or 'unknown error'}")


def expand_query(query: str) -> list[str]:
    if not is_ai_enabled():
        return []
    prompt = (
        "You rewrite search queries for a Chinese business knowledge base.\n"
        "Return 2 to 4 short alternative queries in the same language as the original query.\n"
        "Do not broaden the meaning, do not explain, and return JSON only.\n\n"
        "User query:\n{query}\n\nJSON:"
    )
    try:
        raw = _invoke_prompt(prompt, {"query": query})
        values = _parse_json_payload(raw)
        if not isinstance(values, list):
            return []
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in values:
            if isinstance(item, str):
                text = item.strip()
                if text and text != query and text not in seen:
                    seen.add(text)
                    cleaned.append(text)
        return cleaned[:4]
    except Exception:
        return []


def build_extractive_summary(content: str) -> str:
    paragraphs = [part.strip() for part in content.splitlines() if part.strip()]
    selected: list[str] = []
    for paragraph in paragraphs:
        selected.append(paragraph)
        if len(selected) >= 6:
            break
    if not selected:
        return "No summary is available yet."
    return "\n\n".join(selected)


def summarize_article(title: str, content: str) -> str:
    fallback = build_extractive_summary(content)
    if not is_ai_enabled():
        return fallback
    prompt = (
        "You are an editor for a Chinese business knowledge product.\n"
        "Summarize the article into a high-density Markdown brief.\n"
        "Keep the original logic, do not invent facts, avoid filler, and answer in the same language as the article.\n"
        "Target 6 to 10 short sections or bullets.\n\n"
        "Title:\n{title}\n\n"
        "Article:\n{content}\n\n"
        "Summary:"
    )
    try:
        return _invoke_prompt(prompt, {"title": title, "content": content[:18000]})
    except Exception:
        return fallback


def answer_with_sources(question: str, history: str, context_blocks: str, response_language: str = "auto") -> str:
    language_instruction = "Use the same language as the user question."
    if response_language == "zh":
        language_instruction = "Respond in concise, professional Simplified Chinese."
    elif response_language == "en":
        language_instruction = "Respond in concise, polished English."
    prompt = (
        "You are a business knowledge assistant.\n"
        "Answer only from the supplied materials and never invent facts.\n"
        "If the evidence is insufficient, say that clearly.\n"
        "Respond in Markdown and cite sources with [1], [2], etc.\n"
        f"{language_instruction}\n\n"
        "Conversation history:\n{history}\n\n"
        "User question:\n{question}\n\n"
        "Materials:\n{context_blocks}\n\n"
        "Answer:"
    )
    return _invoke_prompt(
        prompt,
        {"question": question, "history": history or "None", "context_blocks": context_blocks},
    )


def rerank_search_results(query: str, candidates: list[dict]) -> dict[int, float]:
    if not is_ai_enabled() or not candidates:
        return {}
    prompt = (
        "You rerank search results for a business knowledge base.\n"
        "Score each candidate from 0 to 10 based only on relevance to the user query.\n"
        'Return JSON only in this format: [{"id": 1, "score": 8.6}].\n\n'
        "User query:\n{query}\n\n"
        "Candidates:\n{candidates}\n\nJSON:"
    )
    try:
        raw = _invoke_prompt(
            prompt,
            {"query": query, "candidates": json.dumps(candidates, ensure_ascii=False)},
        )
        values = _parse_json_payload(raw)
        if not isinstance(values, list):
            return {}
        scores: dict[int, float] = {}
        for item in values:
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("id")
            score = item.get("score")
            if isinstance(candidate_id, int) and isinstance(score, (int, float)):
                scores[candidate_id] = max(0.0, min(float(score), 10.0))
        return scores
    except Exception:
        return {}


def suggest_editorial_metadata(title: str, content: str) -> dict:
    if not is_ai_enabled():
        return {}
    prompt = (
        "You are helping an editorial CMS for a Chinese business knowledge site.\n"
        "Read the article title and content, then return strict JSON with this shape:\n"
        "{\n"
        '  "excerpt": "80-140 Chinese characters summary",\n'
        '  "article_type": "short type label",\n'
        '  "main_topic": "primary topic label",\n'
        '  "column_slug": "insights|industry|research|deans-view",\n'
        '  "tags": [{"name": "tag name", "category": "topic|industry|type|entity", "confidence": 0.0}]\n'
        "}\n"
        "Use concise Chinese labels when possible, do not invent facts, return 4 to 8 tags, and return JSON only.\n\n"
        "Title:\n{title}\n\n"
        "Content:\n{content}\n\nJSON:"
    )
    try:
        raw = _invoke_prompt(prompt, {"title": title, "content": content[:12000]})
        payload = _parse_json_payload(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def auto_format_editorial_markdown(
    *,
    title: str,
    source_markdown: str,
    excerpt: str,
    main_topic: str,
    article_type: str,
    organization: str,
    tags: list[str] | None = None,
    layout_mode: str = "auto",
    formatting_notes: str = "",
) -> dict[str, str]:
    normalized_title = str(title or "").strip() or "未命名文稿"
    normalized_source = str(source_markdown or "").strip()
    if not normalized_source:
        raise RuntimeError("Source markdown is empty.")

    layout_guidance = LAYOUT_MODE_GUIDANCE.get(layout_mode, LAYOUT_MODE_GUIDANCE["auto"])
    tags_text = ", ".join(tag.strip() for tag in (tags or []) if str(tag).strip())
    prompt = (
        "You are the formatting engine for a top-tier Chinese WeChat official-account editorial CMS.\n"
        "Rewrite the source into publication-ready Markdown only.\n"
        "Hard requirements:\n"
        "1. Use model-side judgment to create a readable, professional Chinese long-form layout similar to the automatic layout mode used by high-end WeChat publishing tools.\n"
        "2. Keep every important fact, number, company name, quote, and conclusion. Do not invent facts.\n"
        "3. The first heading must be a single H1 title.\n"
        "4. Add a short lead paragraph after the title when useful.\n"
        "5. Use clean H2/H3 hierarchy, short paragraphs, lists, and quotes where appropriate.\n"
        "6. Preserve interview, dialogue, and speech structure when present.\n"
        "7. Do not output HTML. Do not output code fences. Output Markdown only.\n"
        "8. Do not mention the model, prompt, or formatting rules in the answer.\n\n"
        f"Layout mode guidance: {layout_guidance}\n"
        f"Additional editorial notes: {formatting_notes or 'None'}\n\n"
        "Metadata:\n"
        f"- Title: {normalized_title}\n"
        f"- Excerpt hint: {excerpt or 'None'}\n"
        f"- Main topic: {main_topic or 'None'}\n"
        f"- Article type: {article_type or 'None'}\n"
        f"- Organization: {organization or 'None'}\n"
        f"- Tags: {tags_text or 'None'}\n\n"
        "Source content:\n"
        f"{normalized_source}\n"
    )

    markdown = _strip_code_fence(
        _request_gemini_text(
            prompt=prompt,
            model_name=GEMINI_EDITORIAL_FORMAT_MODEL,
            response_mime_type="text/plain",
        )
    )
    if not markdown:
        raise RuntimeError("Gemini returned empty formatted content.")
    if not markdown.lstrip().startswith("#"):
        markdown = f"# {normalized_title}\n\n{markdown}"
    return {
        "markdown": markdown.strip(),
        "model": GEMINI_EDITORIAL_FORMAT_MODEL,
    }


def translate_article_to_english(title: str, excerpt: str, content: str) -> dict[str, str]:
    flash_llm = get_flash_llm()
    if flash_llm is None:
        raise RuntimeError("Gemini Flash translation is not configured.")

    prompt = (
        "You are translating a Chinese business article for an English-language knowledge product.\n"
        "Translate the title, short deck, summary, and full visible content into polished professional English.\n"
        "Preserve structure, headings, lists, quotations, and paragraph breaks.\n"
        "Do not invent facts and do not omit visible source content.\n"
        "Return strict JSON only with this shape:\n"
        "{\n"
        '  "title": "English title",\n'
        '  "excerpt": "English deck or short intro",\n'
        '  "summary": "Markdown summary in English",\n'
        '  "content": "Full translated content in Markdown"\n'
        "}\n\n"
        "Source title:\n{title}\n\n"
        "Source excerpt:\n{excerpt}\n\n"
        "Source content:\n{content}\n\nJSON:"
    )
    raw = _invoke_prompt(
        prompt,
        {"title": title, "excerpt": excerpt or "", "content": content or ""},
        llm=flash_llm,
    )
    payload = _parse_json_payload(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini Flash returned an invalid translation payload.")

    translated_title = str(payload.get("title") or "").strip() or title
    translated_excerpt = str(payload.get("excerpt") or "").strip() or excerpt
    translated_summary = str(payload.get("summary") or "").strip()
    translated_content = str(payload.get("content") or "").strip() or content

    if not translated_summary:
        translated_summary = translated_excerpt or translated_content.splitlines()[0]

    return {
        "title": translated_title,
        "excerpt": translated_excerpt,
        "summary": translated_summary,
        "content": translated_content,
        "model": GEMINI_FLASH_MODEL,
    }
