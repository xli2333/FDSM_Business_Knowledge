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
from backend.services.html_renderer import strip_markdown

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


EDITORIAL_SUMMARY_MIN_CHARS = 200
EDITORIAL_SUMMARY_MAX_CHARS = 800
EDITORIAL_SUMMARY_MIN_BULLETS = 3
EDITORIAL_SUMMARY_MAX_BULLETS = 4
EDITORIAL_SUMMARY_DEFAULT_BULLET_LABELS = (
    "\u73b0\u8c61\u5c42\u9762",
    "\u673a\u5236\u5c42\u9762",
    "\u5f71\u54cd\u5c42\u9762",
    "\u5546\u4e1a\u5224\u65ad",
)
_EDITORIAL_SUMMARY_COLON_PATTERN = r"(?:[:\uff1a]|锛\?|閿\?)"
_EDITORIAL_SUMMARY_META_LEAD_RE = re.compile(
    r"^(?:below is|here is|the following is|this summary|this article|the article|"
    r"\u4ee5\u4e0b\u662f|\u4e0b\u9762\u662f|\u672c\u6587|\u672c\u7bc7\u6587\u7ae0|"
    r"\u8fd9\u7bc7\u6587\u7ae0|\u8fd9\u7bc7\u62a5\u9053|\u8fd9\u662f\u4e00\u7bc7|"
    r"\u8fd9\u662f\u4e00\u4efd|\u672c\u6458\u8981)"
    r".{0,80}?(?:brief|digest|summary|abstract|"
    r"\u7b80\u62a5|\u6458\u8981|\u6982\u89c8|\u6897\u6982|\u603b\u7ed3|\u8981\u70b9)?"
    rf"{_EDITORIAL_SUMMARY_COLON_PATTERN}?\s*",
    flags=re.IGNORECASE,
)
_EDITORIAL_SUMMARY_META_START_RE = re.compile(
    r"^(?:below|here|the following|this|"
    r"\u4ee5\u4e0b|\u4e0b\u9762|\u672c\u6587|\u672c\u7bc7|"
    r"\u8fd9\u7bc7|\u8fd9\u662f\u4e00)",
    flags=re.IGNORECASE,
)
_EDITORIAL_SUMMARY_META_COLON_RE = re.compile(
    r"^.{0,80}?(?:brief|digest|summary|abstract|"
    r"\u7b80\u62a5|\u6458\u8981|\u6982\u89c8|\u6897\u6982|\u603b\u7ed3|\u8981\u70b9)?"
    rf"{_EDITORIAL_SUMMARY_COLON_PATTERN}\s*",
    flags=re.IGNORECASE,
)
_EDITORIAL_SUMMARY_GENERIC_LINE_RE = re.compile(
    r"^(?:summary|abstract|digest|brief|"
    r"\u6458\u8981|\u6838\u5fc3\u6458\u8981|\u6838\u5fc3\u89c2\u70b9|\u8981\u70b9|"
    r"\u6838\u5fc3\u5224\u65ad|\u7b80\u62a5|\u5546\u4e1a\u77e5\u8bc6\u7b80\u62a5)$",
    flags=re.IGNORECASE,
)
_EDITORIAL_SUMMARY_HEADING_PREFIX_RE = re.compile(r"^#{1,6}\s+")
_EDITORIAL_SUMMARY_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)")
_EDITORIAL_SUMMARY_SHORT_LABEL_RE = re.compile(
    rf"^(?P<label>[^:\uff1a]{{2,16}}){_EDITORIAL_SUMMARY_COLON_PATTERN}\s*(?P<body>.+)$"
)
_EDITORIAL_SUMMARY_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\u3002\uff01\uff1f?!\uff1b;])\s*")
_EDITORIAL_SUMMARY_STRONG_RE = re.compile(r"\*\*(.+?)\*\*")


def _strip_inline_markdown_tokens(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    value = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"\1", value)
    value = re.sub(r"`(.+?)`", r"\1", value)
    return value.strip()


def _repair_editorial_summary_artifacts(text: str) -> str:
    value = str(text or "")
    replacements = {
        "锛?": "\uff1a",
        "閿?": "\uff1a",
        "銆?": "\u3002",
        "閵?": "\u3002",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def _normalize_editorial_summary_sentence(text: str) -> str:
    value = _repair_editorial_summary_artifacts(_strip_inline_markdown_tokens(text))
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    if not re.search(r"[\u3002\uff01\uff1f?!\uff1b;.]$", value):
        value = f"{value}\u3002"
    return value


def _strip_editorial_summary_meta_lead(text: str) -> str:
    value = _repair_editorial_summary_artifacts(str(text or "").strip())
    previous = None
    while value and value != previous:
        previous = value
        value = _EDITORIAL_SUMMARY_META_LEAD_RE.sub("", value, count=1).strip()
        if _EDITORIAL_SUMMARY_META_START_RE.match(previous):
            value = _EDITORIAL_SUMMARY_META_COLON_RE.sub("", value, count=1).strip()
        value = re.sub(
            rf"^(?:\u7684)?(?:summary|abstract|digest|brief|"
            rf"\u6458\u8981|\u7b80\u62a5|\u6982\u89c8|\u603b\u7ed3){_EDITORIAL_SUMMARY_COLON_PATTERN}\s*",
            "",
            value,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
    return value


def _looks_like_editorial_summary_heading(text: str) -> bool:
    value = _repair_editorial_summary_artifacts(str(text or "").strip())
    if not value or len(value) > 40:
        return False
    if re.search(r"[\u3002\uff01\uff1f?!\uff1b;]", value):
        return False
    match = _EDITORIAL_SUMMARY_SHORT_LABEL_RE.match(value)
    if match:
        return editorial_summary_visible_length(match.group("body")) <= 18
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9&/（）()·\-\s]+", value))


def editorial_summary_visible_length(text: str) -> int:
    value = _repair_editorial_summary_artifacts(str(text or "").strip())
    if not value:
        return 0
    value = _EDITORIAL_SUMMARY_STRONG_RE.sub(r"\1", value)
    value = re.sub(r"(?m)^[-*+]\s+", "", value)
    value = value.replace("\n", "")
    value = re.sub(r"\s+", "", value)
    return len(value)


def _split_editorial_summary_sentences(text: str) -> list[str]:
    normalized = _repair_editorial_summary_artifacts(str(text or "").replace("\r\n", "\n").replace("\r", "\n"))
    if not normalized.strip():
        return []
    sentences: list[str] = []
    for fragment in _EDITORIAL_SUMMARY_SENTENCE_SPLIT_RE.split(normalized.replace("\n", " ")):
        sentence = _normalize_editorial_summary_sentence(fragment)
        if sentence:
            sentences.append(sentence)
    return sentences


def _truncate_editorial_summary_text(text: str, *, max_chars: int = EDITORIAL_SUMMARY_MAX_CHARS) -> str:
    value = _normalize_editorial_summary_sentence(text)
    if not value:
        return ""
    if len(value) <= max_chars:
        return value
    clipped = value[:max_chars].rstrip("\uff0c\u3001\uff1b;:\uff1a ")
    if clipped and not re.search(r"[\u3002\uff01\uff1f?!\uff1b;.]$", clipped):
        clipped = f"{clipped}\u3002"
    return clipped


def _extract_editorial_summary_label(raw_text: str) -> tuple[str | None, str]:
    plain = _repair_editorial_summary_artifacts(_strip_inline_markdown_tokens(raw_text))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return None, ""
    match = _EDITORIAL_SUMMARY_SHORT_LABEL_RE.match(plain)
    if not match:
        return None, plain
    label = match.group("label").strip().rstrip("：:")
    body = match.group("body").strip()
    if not label or not body:
        return None, plain
    return label[:16], body


def _ensure_editorial_summary_emphasis(text: str) -> str:
    value = _repair_editorial_summary_artifacts(str(text or "").strip())
    if not value or "**" in value:
        return value
    candidate = re.split(r"[，。；：:、\s]", value, maxsplit=1)[0].strip()
    candidate = candidate[:14].strip()
    if len(candidate) < 4:
        candidate = value[: min(12, len(value))].rstrip("，。；：:、 ")
    if len(candidate) >= 4:
        return value.replace(candidate, f"**{candidate}**", 1)
    return value


def _format_editorial_summary_bullet(
    label: str | None,
    body: str,
    index: int,
) -> str:
    label_value = _repair_editorial_summary_artifacts(str(label or "").strip()).rstrip("：:")
    if not label_value:
        label_value = EDITORIAL_SUMMARY_DEFAULT_BULLET_LABELS[index % len(EDITORIAL_SUMMARY_DEFAULT_BULLET_LABELS)]
    normalized_body = _normalize_editorial_summary_sentence(body)
    normalized_body = re.sub(rf"^{re.escape(label_value)}{_EDITORIAL_SUMMARY_COLON_PATTERN}\s*", "", normalized_body).strip()
    return f"- **{label_value}\uff1a** {normalized_body}"


def _build_editorial_summary_intro(
    sentences: list[str],
    *,
    target_min_chars: int = 90,
    max_chars: int = 220,
) -> tuple[str, list[str]]:
    remaining = list(sentences)
    intro_parts: list[str] = []
    while remaining and editorial_summary_visible_length("".join(intro_parts)) < target_min_chars:
        candidate = "".join([*intro_parts, remaining[0]])
        if intro_parts and editorial_summary_visible_length(candidate) > max_chars:
            break
        intro_parts.append(remaining.pop(0))
    if not intro_parts and remaining:
        intro_parts.append(remaining.pop(0))
    intro_paragraph = _normalize_editorial_summary_sentence("".join(intro_parts))
    return _ensure_editorial_summary_emphasis(intro_paragraph), remaining


def _render_editorial_summary(
    intro_paragraph: str,
    selected_bullets: list[tuple[str | None, str]],
    trailing_paragraph: str,
) -> str:
    parts: list[str] = []
    if intro_paragraph:
        parts.append(intro_paragraph)
    if selected_bullets:
        bullet_lines = [
            _format_editorial_summary_bullet(label, body, index)
            for index, (label, body) in enumerate(selected_bullets)
        ]
        parts.append("\n".join(bullet_lines))
    if trailing_paragraph:
        parts.append(_ensure_editorial_summary_emphasis(trailing_paragraph))
    return "\n\n".join(part for part in parts if part).strip()


def normalize_editorial_summary_output(
    text: str,
    *,
    min_chars: int = EDITORIAL_SUMMARY_MIN_CHARS,
    max_chars: int = EDITORIAL_SUMMARY_MAX_CHARS,
) -> str:
    lines = _repair_editorial_summary_artifacts(str(text or "").replace("\r\n", "\n").replace("\r", "\n")).split("\n")
    del min_chars
    del max_chars
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []
    bullet_index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        paragraph = _normalize_editorial_summary_sentence(" ".join(paragraph_lines))
        if paragraph:
            blocks.append(("paragraph", paragraph))
        paragraph_lines = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue

        was_heading = bool(_EDITORIAL_SUMMARY_HEADING_PREFIX_RE.match(stripped))
        was_list = bool(_EDITORIAL_SUMMARY_LIST_PREFIX_RE.match(stripped))
        normalized_raw = _EDITORIAL_SUMMARY_HEADING_PREFIX_RE.sub("", stripped)
        normalized_raw = _EDITORIAL_SUMMARY_LIST_PREFIX_RE.sub("", normalized_raw)
        plain = _repair_editorial_summary_artifacts(_strip_inline_markdown_tokens(normalized_raw))
        if not paragraph_lines and not blocks:
            normalized_raw = _strip_editorial_summary_meta_lead(normalized_raw)
            plain = _strip_editorial_summary_meta_lead(plain)
        if not plain:
            continue
        if _EDITORIAL_SUMMARY_GENERIC_LINE_RE.match(plain):
            continue
        if was_heading:
            continue
        if not paragraph_lines and not blocks and _looks_like_editorial_summary_heading(plain):
            continue

        label, body = _extract_editorial_summary_label(normalized_raw)
        if was_list:
            if body:
                flush_paragraph()
                blocks.append(("bullet", _format_editorial_summary_bullet(label, body, bullet_index)))
                bullet_index += 1
            continue
        if label and editorial_summary_visible_length(body) >= 18:
            flush_paragraph()
            blocks.append(("bullet", _format_editorial_summary_bullet(label, body, bullet_index)))
            bullet_index += 1
            continue

        plain = re.sub(r"\s+", " ", plain).strip()
        if plain:
            paragraph_lines.append(plain)

    flush_paragraph()

    if not blocks:
        return ""

    if "**" not in "\n".join(text for _, text in blocks):
        for index, (kind, value) in enumerate(blocks):
            if kind == "paragraph":
                blocks[index] = (kind, _ensure_editorial_summary_emphasis(value))
                break
        else:
            blocks[0] = (blocks[0][0], _ensure_editorial_summary_emphasis(blocks[0][1]))

    rendered: list[str] = []
    previous_kind = ""
    for kind, value in blocks:
        if not value:
            continue
        if rendered and not (previous_kind == "bullet" and kind == "bullet"):
            rendered.append("")
        rendered.append(value)
        previous_kind = kind
    return _repair_editorial_summary_artifacts("\n".join(rendered)).strip()


def build_extractive_summary(content: str) -> str:
    paragraphs = [part.strip() for part in str(content or "").splitlines() if part.strip()]
    if not paragraphs:
        return "No summary is available yet."
    fallback = ""
    for limit in (10, 16, 24, len(paragraphs)):
        candidate = normalize_editorial_summary_output("\n\n".join(paragraphs[:limit]))
        if candidate:
            fallback = candidate
        if editorial_summary_visible_length(candidate) >= EDITORIAL_SUMMARY_MIN_CHARS:
            return candidate
    return fallback or "No summary is available yet."


def _build_editorial_content_window(content: str, *, max_chars: int = 16000, tail_chars: int = 4000) -> str:
    normalized = str(content or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    head_chars = max(4000, max_chars - tail_chars)
    head = normalized[:head_chars].rstrip()
    tail = normalized[-tail_chars:].lstrip()
    return f"{head}\n\n[中段内容省略]\n\n{tail}"


def summarize_article_payload(title: str, content: str) -> dict[str, str]:
    fallback = build_extractive_summary(content)
    content_window = str(content or "").strip()
    if not is_ai_enabled():
        return {"summary": fallback, "model": "extractive-fallback"}
    prompt = (
        "You are an editor for a Chinese business knowledge product.\n"
        "Write a complete article summary that still reads compactly.\n"
        "Hard requirements:\n"
        "1. Return the summary body only.\n"
        "2. Aim for roughly 320 to 1200 Chinese characters when the source supports it, but never cut off the article's later-stage judgment just to stay short.\n"
        "3. Start with one opening paragraph that explains the article as a whole.\n"
        "4. When bullets help readability, use 3 to 5 Markdown bullet points for the main dimensions, but do not let the entire answer become only a bullet list.\n"
        "5. End with one short closing paragraph that closes the overall business judgment, implication, or conclusion from the full article.\n"
        "6. Keep 1 to 3 key phrases visibly emphasized with Markdown bold.\n"
        "7. Do not add any prefatory phrases such as 'Below is', 'Here is', '以下是', '下面是', '本文', or '这篇文章'.\n"
        "8. Do not write a title, heading, numbered outline, section label, digest framing, or brief framing.\n"
        "9. Preserve the article's core facts, logic, middle argument, and ending implications without inventing anything.\n"
        "10. Use the same language as the article.\n"
        "11. Output Markdown only.\n\n"
        "Title:\n{title}\n\n"
        "Article:\n{content}\n\n"
        "Summary:"
    )
    try:
        summary = normalize_editorial_summary_output(
            _invoke_prompt(prompt, {"title": title, "content": content_window})
        )
        summary_length = editorial_summary_visible_length(summary)
        fallback_length = editorial_summary_visible_length(fallback)
        if summary_length < EDITORIAL_SUMMARY_MIN_CHARS and fallback_length >= EDITORIAL_SUMMARY_MIN_CHARS:
            summary = fallback
        elif summary_length < EDITORIAL_SUMMARY_MIN_CHARS and fallback_length > summary_length:
            summary = fallback
        return {
            "summary": summary or fallback,
            "model": GEMINI_CHAT_MODEL,
        }
    except Exception:
        return {"summary": fallback, "model": "extractive-fallback"}


def summarize_article(title: str, content: str) -> str:
    return summarize_article_payload(title, content)["summary"]


def _compact_media_copy_text(value: str | None) -> str:
    normalized = strip_markdown(str(value or "").replace("\r\n", "\n").replace("\r", "\n"))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _truncate_media_copy_text(value: str, *, max_chars: int) -> str:
    compact = _compact_media_copy_text(value)
    if not compact:
        return ""
    if len(compact) <= max_chars:
        return compact
    clipped = compact[:max_chars].rstrip("，。；：:、 ")
    if clipped and not re.search(r"[。！？!?]$", clipped):
        clipped = f"{clipped}。"
    return clipped


_MEDIA_SUMMARY_META_LEAD_RE = re.compile(
    r"^(?:以下是|下面是|节目摘要如下|摘要如下|本期节目摘要|节目摘要|summary|program summary|brief summary)\s*(?:[:：-]\s*)?",
    flags=re.IGNORECASE,
)
_MEDIA_SUMMARY_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)")
_MEDIA_SUMMARY_HEADING_PREFIX_RE = re.compile(r"^#{1,6}\s+")


def _strip_media_summary_meta(text: str) -> str:
    normalized = _strip_code_fence(str(text or "").replace("\r\n", "\n").replace("\r", "\n"))
    cleaned_lines: list[str] = []
    for raw_line in normalized.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        stripped = _MEDIA_SUMMARY_HEADING_PREFIX_RE.sub("", stripped)
        stripped = _MEDIA_SUMMARY_LIST_PREFIX_RE.sub("", stripped)
        stripped = _MEDIA_SUMMARY_META_LEAD_RE.sub("", stripped, count=1).strip()
        if stripped:
            cleaned_lines.append(stripped)
    return "\n".join(cleaned_lines).strip()


def _strip_media_summary_label(text: str) -> str:
    return re.sub(
        r"^(?:节目摘要|摘要|核心摘要|program summary|summary|overview)\s*(?:[:：-]\s*)?",
        "",
        str(text or "").strip(),
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def normalize_media_summary_markdown(text: str, *, max_chars: int = 180) -> str:
    compact = _truncate_media_copy_text(_strip_media_summary_meta(text), max_chars=max_chars)
    compact = _strip_media_summary_label(compact)
    if not compact:
        return ""
    label = "节目摘要" if re.search(r"[\u4e00-\u9fff]", compact) else "Program summary"
    punctuation = "：" if label == "节目摘要" else ":"
    return f"**{label}{punctuation}** {compact}"


_MEDIA_CHAPTER_LABEL_PATTERN = r"(?:\d{1,2}:)?\d{1,2}:\d{2}"
_MEDIA_CHAPTER_HEADER_RE = re.compile(
    rf"^(?:[-*+]\s*)?(?:(?:发言人|主持人|嘉宾|主播|主讲人|旁白|讲者|Speaker|Host|Guest|Presenter|Anchor|Narrator|Interviewer|Interviewee)"
    r"(?:[\s#：:.\-]*[\w\u4e00-\u9fff-]{1,20})?\s+)?(?P<label>"
    rf"{_MEDIA_CHAPTER_LABEL_PATTERN})"
    r"(?:\s*(?:[-—–|：:]\s*)?(?P<body>.+))?$",
    re.IGNORECASE,
)
_MEDIA_CHAPTER_TITLE_PREFIX_RE = re.compile(
    r"^(?:章节|目录|章节目录|chapter|section)\s*(?:标题|title)?\s*(?:[:：-]\s*)?",
    re.IGNORECASE,
)
_MEDIA_CHAPTER_CATEGORY_PREFIX_RE = re.compile(
    r"^(?:问题引入|核心悬念|行业背景|招股书拆解|决策视角|案例拆解|发布收口|经营判断|资本路径|章节[一二三四五六七八九十0-9]+|part\s*\d+|section\s*\d+|chapter\s*\d+)\s*(?:[:：-]\s*)",
    re.IGNORECASE,
)
_MEDIA_CHAPTER_SHORT_LABEL_RE = re.compile(r"^(?P<label>[^:：]{1,8})\s*[:：]\s*(?P<body>.+)$")
_MEDIA_CHAPTER_TITLE_FILLER_RE = re.compile(
    r"^(?:这一部分|这一段|本段|本节|这一章|本章节|这里主要|本部分|这一部分主要在讲|这一段主要在讲)\s*",
    re.IGNORECASE,
)
_MEDIA_CHAPTER_TRAILING_PUNCT_RE = re.compile(r"[，,；;：:。！？!?、]+$")
_MEDIA_CHAPTER_GENERIC_LABELS = {
    "问题引入",
    "核心悬念",
    "行业背景",
    "招股书拆解",
    "决策视角",
    "案例拆解",
    "发布收口",
    "经营判断",
    "资本路径",
    "章节",
    "chapter",
    "section",
    "part",
}


def _normalize_media_chapter_label(label: str | None) -> str:
    raw = str(label or "").strip()
    if not raw:
        return ""
    parts = raw.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return ""
    if len(numbers) == 2:
        minutes, seconds = numbers
        return f"{minutes:02d}:{seconds:02d}"
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return ""


def _media_chapter_label_to_seconds(label: str) -> int:
    parts = [int(part) for part in str(label or "").split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return max(0, minutes * 60 + seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return max(0, hours * 3600 + minutes * 60 + seconds)
    return 0


def _extract_media_timestamp_candidates(source_text: str, *, max_items: int = 12) -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    normalized = str(source_text or "").replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in normalized.split("\n"):
        compact = _compact_media_copy_text(strip_markdown(raw_line))
        if not compact:
            continue
        match = _MEDIA_CHAPTER_HEADER_RE.match(compact)
        if not match:
            continue
        label = _normalize_media_chapter_label(match.group("label"))
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= max_items:
            break
    return labels


def normalize_media_chapter_title(text: str | None, *, max_chars: int = 30) -> str:
    compact = _compact_media_copy_text(strip_markdown(text or ""))
    compact = _MEDIA_CHAPTER_TITLE_PREFIX_RE.sub("", compact, count=1).strip()
    compact = _MEDIA_CHAPTER_CATEGORY_PREFIX_RE.sub("", compact, count=1).strip()
    compact = _MEDIA_CHAPTER_TITLE_FILLER_RE.sub("", compact, count=1).strip()
    short_label_match = _MEDIA_CHAPTER_SHORT_LABEL_RE.match(compact)
    if short_label_match:
        label = short_label_match.group("label").strip().lower()
        body = short_label_match.group("body").strip()
        if label in {item.lower() for item in _MEDIA_CHAPTER_GENERIC_LABELS} or len(label) <= 6:
            compact = body
    compact = compact.replace("：", " ").replace(":", " ")
    compact = compact.strip("-—–:：[]()（） ")
    compact = _MEDIA_CHAPTER_TRAILING_PUNCT_RE.sub("", compact).strip()
    return _truncate_media_copy_text(compact, max_chars=max_chars) if compact else ""


def _media_chapter_title_signature(text: str | None) -> str:
    compact = normalize_media_chapter_title(text, max_chars=40).lower()
    compact = re.sub(r"\s+", "", compact)
    compact = re.sub(r"[，,；;：:。！？!?、\-\[\]()（）]", "", compact)
    return compact


def media_generated_chapters_need_revision(chapters: list[dict] | None) -> bool:
    if not chapters:
        return False
    seen_signatures: set[str] = set()
    for item in chapters:
        title = str(item.get("title") or "").strip()
        signature = _media_chapter_title_signature(title)
        if not title or not signature:
            return True
        if "：" in title or ":" in title:
            return True
        if signature in seen_signatures:
            return True
        seen_signatures.add(signature)
    return False


def normalize_media_generated_chapters(chapters, *, source_text: str, max_items: int = 8) -> list[dict]:
    if not isinstance(chapters, list):
        return []

    allowed_labels = _extract_media_timestamp_candidates(source_text, max_items=max(12, max_items * 2))
    if not allowed_labels:
        return []
    allowed_set = set(allowed_labels)
    order_map = {label: index for index, label in enumerate(allowed_labels)}

    normalized_items: list[dict] = []
    seen_labels: set[str] = set()
    seen_title_signatures: set[str] = set()
    for item in chapters:
        if not isinstance(item, dict):
            continue
        label = _normalize_media_chapter_label(
            item.get("timestamp_label") or item.get("timestamp") or item.get("time") or item.get("label")
        )
        title = normalize_media_chapter_title(
            item.get("title") or item.get("heading") or item.get("summary") or item.get("name")
        )
        signature = _media_chapter_title_signature(title)
        if not label or not title or not signature or label not in allowed_set or label in seen_labels or signature in seen_title_signatures:
            continue
        seen_labels.add(label)
        seen_title_signatures.add(signature)
        normalized_items.append(
            {
                "timestamp_label": label,
                "timestamp_seconds": _media_chapter_label_to_seconds(label),
                "title": title,
            }
        )

    normalized_items.sort(
        key=lambda item: (
            order_map.get(item["timestamp_label"], len(order_map)),
            int(item.get("timestamp_seconds") or 0),
        )
    )
    return normalized_items[:max_items]


def _normalize_media_generation_source_value(value: str | None) -> str:
    normalized = str(value or "").strip()
    if normalized.lower() in {"none", "null", "undefined"}:
        return ""
    return normalized


def _resolve_media_generation_source_text(*, transcript_markdown: str, script_markdown: str) -> str:
    transcript_text = _normalize_media_generation_source_value(transcript_markdown)
    if transcript_text:
        return transcript_text
    return _normalize_media_generation_source_value(script_markdown)


def generate_media_chapter_outline(
    *,
    title: str,
    kind: str,
    speaker: str,
    series_name: str,
    transcript_markdown: str,
    script_markdown: str,
) -> dict[str, object]:
    source_text = _resolve_media_generation_source_text(
        transcript_markdown=transcript_markdown,
        script_markdown=script_markdown,
    )
    if not source_text:
        raise RuntimeError("Media chapter source is empty.")

    timestamp_candidates = _extract_media_timestamp_candidates(source_text)
    if not timestamp_candidates:
        return {
            "chapters": [],
            "model": "timestamp-unavailable",
        }
    if not is_ai_enabled():
        return {
            "chapters": [],
            "model": "extractive-fallback",
        }

    timestamp_hint_block = "\n".join(f"- {label}" for label in timestamp_candidates)
    prompt = (
        "You are helping a Chinese business knowledge media CMS produce a chapter outline for an audio or video program.\n"
        "Return strict JSON only with this shape:\n"
        "{\n"
        '  "chapters": [{"timestamp_label": "00:00", "title": "主题化目录标题"}]\n'
        "}\n"
        "Hard requirements:\n"
        "1. Use only the timestamps from the detected list below. Never invent a new timestamp.\n"
        "2. Keep chapters in chronological order.\n"
        "3. Each title must summarize what that section is about, not quote the raw opening sentence.\n"
        "4. Remove oral fillers such as 欢迎来到、看完之后、然后、最后 and similar spoken transitions.\n"
        "5. Keep titles lightweight and outline-style. Prefer 8-24 Chinese characters or 3-8 English words.\n"
        "6. Do not use category labels or prefixes such as 问题引入、核心悬念、行业背景、招股书拆解、决策视角、案例拆解、发布收口.\n"
        "7. Do not use : or ： in the title. Write the topic directly as a standalone heading.\n"
        "8. Make the titles mutually distinct. If two adjacent sections discuss different things, the titles must also be different.\n"
        "9. No Markdown, no numbering, no speaker names, no quotation marks around the title.\n"
        "10. It is acceptable to omit weak timestamps, but keep the strongest 3 to 8 sections when possible.\n\n"
        "Detected timestamps:\n"
        f"{timestamp_hint_block}\n\n"
        f"Title: {title.strip() or '未命名节目'}\n"
        f"Kind: {kind.strip() or 'audio'}\n"
        f"Speaker: {speaker.strip() or 'None'}\n"
        f"Series: {series_name.strip() or 'None'}\n\n"
        f"Source:\n{source_text}\n\nJSON:"
    )
    try:
        raw = _request_gemini_text(
            prompt=prompt,
            model_name=GEMINI_CHAT_MODEL,
            response_mime_type="application/json",
        )
        payload = _parse_json_payload(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Media chapter payload must be a JSON object.")
        chapters_payload = normalize_media_generated_chapters(
            payload.get("chapters"),
            source_text=source_text,
            max_items=8,
        )
        if chapters_payload and media_generated_chapters_need_revision(chapters_payload):
            revision_prompt = (
                "You are revising a chapter outline for a Chinese business knowledge media CMS.\n"
                "Return strict JSON only with this shape:\n"
                "{\n"
                '  "chapters": [{"timestamp_label": "00:00", "title": "直接说明这部分讲什么"}]\n'
                "}\n"
                "Rewrite only the titles. Keep the timestamps from the draft outline.\n"
                "Hard requirements:\n"
                "1. Keep the same timestamp_label values from the draft outline. Never add or delete timestamps.\n"
                "2. Titles must be unique across the array.\n"
                "3. Do not use category labels or prefixes such as 问题引入、核心悬念、行业背景、招股书拆解、决策视角、案例拆解、发布收口.\n"
                "4. Do not use : or ： in any title.\n"
                "5. Each title should directly say what that section is discussing, like a clean article subheading.\n"
                "6. Remove spoken fillers such as 欢迎来到、看完之后、然后、最后 and similar transitions.\n"
                "7. Keep titles concise and concrete.\n\n"
                f"Draft outline:\n{json.dumps(chapters_payload, ensure_ascii=False)}\n\n"
                f"Source:\n{source_text}\n\nJSON:"
            )
            revised_raw = _request_gemini_text(
                prompt=revision_prompt,
                model_name=GEMINI_CHAT_MODEL,
                response_mime_type="application/json",
            )
            revised_payload = _parse_json_payload(revised_raw)
            if isinstance(revised_payload, dict):
                revised_chapters = normalize_media_generated_chapters(
                    revised_payload.get("chapters"),
                    source_text=source_text,
                    max_items=8,
                )
                if revised_chapters and not media_generated_chapters_need_revision(revised_chapters):
                    chapters_payload = revised_chapters
        return {
            "chapters": chapters_payload,
            "model": GEMINI_CHAT_MODEL,
        }
    except Exception:
        return {
            "chapters": [],
            "model": "extractive-fallback",
        }


_MEDIA_BODY_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)")
_MEDIA_BODY_HEADING_PREFIX_RE = re.compile(r"^#{1,6}\s+")
_MEDIA_BODY_TIMESTAMP_LINE_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:\[\s*)?(?:(?:\d{1,2}:)?\d{1,2}:\d{2})(?:\s*\])?\s*(?:[-—–:：]\s*)?(?P<body>.+)$"
)
_MEDIA_BODY_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？?!；;])\s+")


def _normalize_media_highlight_line(text: str, *, max_chars: int = 72) -> str:
    compact = _compact_media_copy_text(text)
    compact = re.sub(r"^(?:transcript|script|节目脚本|节目转录|逐字稿)\s*", "", compact, flags=re.IGNORECASE).strip()
    compact = compact.strip("-—–:：[]()（） ")
    if len(compact) < 4:
        return ""
    return _truncate_media_copy_text(compact, max_chars=max_chars)


def _extract_media_highlights(source_text: str, *, intro_text: str = "", max_items: int = 3) -> list[str]:
    normalized = _strip_code_fence(str(source_text or "").replace("\r\n", "\n").replace("\r", "\n"))
    seen: set[str] = set()
    highlights: list[str] = []
    intro_compact = _compact_media_copy_text(intro_text).lower()

    def push(candidate: str) -> None:
        normalized_candidate = _normalize_media_highlight_line(candidate)
        if not normalized_candidate:
            return
        compact_candidate = _compact_media_copy_text(normalized_candidate).lower()
        if compact_candidate in seen:
            return
        if intro_compact and (compact_candidate in intro_compact or intro_compact in compact_candidate):
            return
        seen.add(compact_candidate)
        highlights.append(normalized_candidate)

    for raw_line in normalized.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        stripped = _MEDIA_BODY_HEADING_PREFIX_RE.sub("", stripped)
        timestamp_match = _MEDIA_BODY_TIMESTAMP_LINE_RE.match(stripped)
        if timestamp_match:
            push(timestamp_match.group("body"))
        else:
            push(_MEDIA_BODY_LIST_PREFIX_RE.sub("", stripped))
        if len(highlights) >= max_items:
            return highlights[:max_items]

    plain_source = strip_markdown(normalized)
    compact_source = re.sub(r"\s+", " ", plain_source).strip()
    if compact_source:
        for sentence in _MEDIA_BODY_SENTENCE_SPLIT_RE.split(compact_source):
            push(sentence)
            if len(highlights) >= max_items:
                break
    return highlights[:max_items]


def normalize_media_body_markdown(text: str, *, summary: str, source_text: str) -> str:
    cleaned = _strip_code_fence(str(text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    cleaned = re.sub(r"^(?:#\s+.*\n+)+", "", cleaned).strip()
    cleaned = re.sub(
        r"^(?:以下是|下面是|节目简介如下|本文|这期节目将).{0,40}?(?:[:：])?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    paragraphs: list[str] = []
    inline_highlights: list[str] = []
    current_paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not current_paragraph:
            return
        paragraph = _truncate_media_copy_text(" ".join(current_paragraph), max_chars=180)
        if paragraph:
            paragraphs.append(paragraph)
        current_paragraph.clear()

    for raw_line in cleaned.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if _MEDIA_BODY_HEADING_PREFIX_RE.match(stripped):
            flush_paragraph()
            continue
        if _MEDIA_BODY_LIST_PREFIX_RE.match(stripped):
            flush_paragraph()
            bullet_text = _MEDIA_BODY_LIST_PREFIX_RE.sub("", stripped)
            normalized_bullet = _normalize_media_highlight_line(bullet_text)
            if normalized_bullet:
                inline_highlights.append(normalized_bullet)
            continue
        current_paragraph.append(stripped)
    flush_paragraph()

    intro_seed = paragraphs[0] if paragraphs else _strip_media_summary_label(_compact_media_copy_text(summary))
    intro = _truncate_media_copy_text(intro_seed or _compact_media_copy_text(source_text), max_chars=160)

    highlights: list[str] = []
    seen_highlights: set[str] = set()
    for candidate in [*inline_highlights, *paragraphs[1:], *_extract_media_highlights(source_text, intro_text=intro, max_items=3)]:
        normalized_candidate = _normalize_media_highlight_line(candidate)
        if not normalized_candidate:
            continue
        compact_candidate = _compact_media_copy_text(normalized_candidate).lower()
        compact_intro = _compact_media_copy_text(intro).lower()
        if compact_candidate in seen_highlights:
            continue
        if compact_intro and (compact_candidate in compact_intro or compact_intro in compact_candidate):
            continue
        seen_highlights.add(compact_candidate)
        highlights.append(normalized_candidate)
        if len(highlights) >= 3:
            break

    parts = ["## 节目简介", ""]
    if intro:
        parts.append(intro)
    if highlights:
        parts.extend(["", "### 核心看点", ""])
        parts.extend([f"- {item}" for item in highlights[:3]])
    return "\n".join(parts).strip()


def _build_media_body_fallback(summary: str, source_text: str) -> str:
    return normalize_media_body_markdown("", summary=summary, source_text=source_text)


def _legacy_generate_media_text_assets(
    *,
    title: str,
    kind: str,
    speaker: str,
    series_name: str,
    transcript_markdown: str,
    script_markdown: str,
) -> dict[str, str]:
    source_text = _resolve_media_generation_source_text(
        transcript_markdown=transcript_markdown,
        script_markdown=script_markdown,
    )
    if not source_text:
        raise RuntimeError("Media copy source is empty.")

    plain_source = _compact_media_copy_text(source_text)
    fallback_summary = normalize_media_summary_markdown(plain_source or title, max_chars=160)
    fallback_body = _build_media_body_fallback(fallback_summary or title, plain_source or title)
    if not is_ai_enabled():
        return {
            "summary": fallback_summary or title,
            "body_markdown": fallback_body,
            "model": "extractive-fallback",
        }

    prompt = (
        "You are helping a Chinese business knowledge media CMS produce copy for an audio or video program.\n"
        "Return strict JSON only with this shape:\n"
        "{\n"
        '  "summary": "Markdown only, 80-180 Chinese characters, one short paragraph with at most one bold lead phrase",\n'
        '  "body_markdown": "Markdown only, start with ## 节目简介, include one short intro paragraph, then optionally add ### 核心看点 with 2 or 3 bullet points"\n'
        "}\n"
        "Hard requirements:\n"
        "1. Keep the same language as the source.\n"
        "2. Do not invent facts beyond the transcript or script.\n"
        "3. Do not add prefatory phrases such as 以下是、下面是、节目简介如下、本文、这期节目将.\n"
        "4. You may add a short bullet list under ### 核心看点, but never output more than 3 bullet points in total and do not add any other extra headings.\n"
        "5. The summary must stay lightweight and directly usable as the media card summary.\n"
        "6. The body_markdown must read like a finished program intro, not a note to the editor.\n"
        "7. Keep the structure lightweight and readable, with one intro paragraph plus up to 3 concise takeaways.\n\n"
        f"Title: {title.strip() or '未命名节目'}\n"
        f"Kind: {kind.strip() or 'audio'}\n"
        f"Speaker: {speaker.strip() or 'None'}\n"
        f"Series: {series_name.strip() or 'None'}\n\n"
        f"Source:\n{source_text}\n\nJSON:"
    )
    try:
        raw = _request_gemini_text(
            prompt=prompt,
            model_name=GEMINI_CHAT_MODEL,
            response_mime_type="application/json",
        )
        payload = _parse_json_payload(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Media copy payload must be a JSON object.")
        summary = normalize_media_summary_markdown(str(payload.get("summary") or fallback_summary), max_chars=180) or fallback_summary or title
        body_markdown = str(payload.get("body_markdown") or "").strip()
        if not body_markdown:
            body_markdown = fallback_body
        body_markdown = re.sub(r"^(?:#\s+.*\n+)+", "", body_markdown).strip()
        if not body_markdown.startswith("## 节目简介"):
            body_markdown = f"## 节目简介\n\n{_truncate_media_copy_text(body_markdown or summary, max_chars=320)}"
        body_markdown = re.sub(
            r"^(?:以下是|下面是|节目简介如下|本文|这期节目将).{0,40}?(?:[:：])?\s*",
            "",
            body_markdown,
            flags=re.I,
        ).strip()
        return {
            "summary": summary,
            "body_markdown": body_markdown,
            "model": GEMINI_CHAT_MODEL,
        }
    except Exception:
        return {
            "summary": fallback_summary or title,
            "body_markdown": fallback_body,
            "model": "extractive-fallback",
        }


def generate_media_text_assets(
    *,
    title: str,
    kind: str,
    speaker: str,
    series_name: str,
    transcript_markdown: str,
    script_markdown: str,
) -> dict[str, object]:
    source_text = _resolve_media_generation_source_text(
        transcript_markdown=transcript_markdown,
        script_markdown=script_markdown,
    )
    if not source_text:
        raise RuntimeError("Media copy source is empty.")

    plain_source = _compact_media_copy_text(source_text)
    fallback_summary = normalize_media_summary_markdown(plain_source or title, max_chars=160)
    fallback_body = _build_media_body_fallback(fallback_summary or title, source_text)
    timestamp_candidates = _extract_media_timestamp_candidates(source_text)
    if not is_ai_enabled():
        return {
            "summary": fallback_summary or title,
            "body_markdown": fallback_body,
            "chapters": [],
            "model": "extractive-fallback",
        }

    timestamp_hint_block = "\n".join(f"- {label}" for label in timestamp_candidates) or "- None"
    prompt = (
        "You are helping a Chinese business knowledge media CMS produce copy for an audio or video program.\n"
        "Return strict JSON only with this shape:\n"
        "{\n"
        '  "summary": "Markdown only, 80-180 Chinese characters, one short paragraph with at most one bold lead phrase",\n'
        '  "body_markdown": "Markdown only, start with ## 节目简介, include one short intro paragraph, then optionally add ### 核心看点 with 2 or 3 bullet points",\n'
        '  "chapters": [{"timestamp_label": "00:00", "title": "主题化目录标题"}]\n'
        "}\n"
        "Hard requirements:\n"
        "1. Keep the same language as the source.\n"
        "2. Do not invent facts beyond the transcript or script.\n"
        "3. Do not add prefatory phrases such as 以下是、下面是、节目简介如下、本文、这期节目将.\n"
        "4. You may add a short bullet list under ### 核心看点, but never output more than 3 bullet points in total and do not add any other extra headings.\n"
        "5. The summary must stay lightweight and directly usable as the media card summary.\n"
        "6. The body_markdown must read like a finished program intro, not a note to the editor.\n"
        "7. Keep the structure lightweight and readable, with one intro paragraph plus up to 3 concise takeaways.\n\n"
        "Chapter rules:\n"
        "8. Use only timestamps from the detected list below. Never invent a new timestamp.\n"
        "9. Chapter titles must summarize what that section is about, not quote the raw opening sentence.\n"
        "10. Remove oral fillers such as 欢迎来到、看完之后、然后、最后 and similar transitions.\n"
        "11. Keep chapter titles lightweight and outline-style, with no Markdown or numbering.\n"
        "12. If the source has no usable timestamps, return an empty chapters array.\n\n"
        "Detected timestamps:\n"
        f"{timestamp_hint_block}\n\n"
        f"Title: {title.strip() or '未命名节目'}\n"
        f"Kind: {kind.strip() or 'audio'}\n"
        f"Speaker: {speaker.strip() or 'None'}\n"
        f"Series: {series_name.strip() or 'None'}\n\n"
        f"Source:\n{source_text}\n\nJSON:"
    )
    try:
        raw = _request_gemini_text(
            prompt=prompt,
            model_name=GEMINI_CHAT_MODEL,
            response_mime_type="application/json",
        )
        payload = _parse_json_payload(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Media copy payload must be a JSON object.")
        summary = normalize_media_summary_markdown(str(payload.get("summary") or fallback_summary), max_chars=180) or fallback_summary or title
        body_markdown = normalize_media_body_markdown(
            str(payload.get("body_markdown") or fallback_body),
            summary=summary,
            source_text=source_text,
        )
        chapters = normalize_media_generated_chapters(
            payload.get("chapters"),
            source_text=source_text,
            max_items=8,
        )
        return {
            "summary": summary,
            "body_markdown": body_markdown,
            "chapters": chapters,
            "model": GEMINI_CHAT_MODEL,
        }
    except Exception:
        return {
            "summary": fallback_summary or title,
            "body_markdown": fallback_body,
            "chapters": [],
            "model": "extractive-fallback",
        }


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
        "Respond in Markdown, but do not use source numbers, bracket citations, or a section called Sources/来源.\n"
        "Use valid Markdown only. Never leave unmatched ** or __ markers.\n"
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
    content_window = _build_editorial_content_window(content)
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
        "Use concise Chinese labels when possible.\n"
        "Prefer specific labels over generic ones.\n"
        "When the article clearly involves companies, people, products, regulators, or laws, keep their official names exactly.\n"
        "Cover multiple dimensions when supported by the text: topic, industry, and entity.\n"
        "Avoid weak tags such as 商业, 企业, 公司, 管理, 作者, 文章, 案例 unless the article is truly about that concept.\n"
        "Return 6 to 12 tags when the article contains enough signal, and return JSON only.\n\n"
        f"Title:\n{title}\n\n"
        f"Content:\n{content_window}\n\nJSON:"
    )
    try:
        raw = _request_gemini_text(
            prompt=prompt,
            model_name=GEMINI_CHAT_MODEL,
            response_mime_type="application/json",
        )
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
        "{{\n"
        '  "title": "English title",\n'
        '  "excerpt": "English deck or short intro",\n'
        '  "summary": "Markdown summary in English",\n'
        '  "content": "Full translated content in Markdown"\n'
        "}}\n\n"
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


def translate_editorial_assets_to_english(
    title: str,
    excerpt: str,
    summary_markdown: str,
    content_markdown: str,
) -> dict[str, str]:
    flash_llm = get_flash_llm()
    if flash_llm is None:
        raise RuntimeError("Gemini Flash translation is not configured.")

    normalized_summary = str(summary_markdown or "").strip()
    normalized_content = str(content_markdown or "").strip()
    if not normalized_summary:
        raise RuntimeError("Chinese summary is empty and cannot be translated.")
    if not normalized_content:
        raise RuntimeError("Chinese content is empty and cannot be translated.")

    prompt = (
        "You are translating an editorial draft for Fudan Business Knowledge into polished publication-quality English.\n"
        "This is an editorial translation task, not a rewrite.\n"
        "Translate the Chinese title, deck, summary markdown, and full body markdown into English.\n"
        "Preserve the original meaning, argument order, headings, bullet lists, tables, quotations, and paragraph breaks.\n"
        "Do not omit any meaningful content. Do not invent facts. Do not add commentary.\n"
        "Return strict JSON only with this shape:\n"
        "{{\n"
        '  "title": "English title",\n'
        '  "excerpt": "English deck or short intro",\n'
        '  "summary": "English markdown summary translated from the Chinese summary",\n'
        '  "content": "Full English markdown body translated from the Chinese body"\n'
        "}}\n\n"
        "Chinese title:\n{title}\n\n"
        "Chinese deck:\n{excerpt}\n\n"
        "Chinese summary markdown:\n{summary_markdown}\n\n"
        "Chinese body markdown:\n{content_markdown}\n\nJSON:"
    )
    raw = _invoke_prompt(
        prompt,
        {
            "title": title or "",
            "excerpt": excerpt or "",
            "summary_markdown": normalized_summary,
            "content_markdown": normalized_content,
        },
        llm=flash_llm,
    )
    payload = _parse_json_payload(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini Flash returned an invalid editorial translation payload.")

    translated_title = str(payload.get("title") or "").strip() or str(title or "").strip()
    translated_excerpt = str(payload.get("excerpt") or "").strip() or str(excerpt or "").strip()
    translated_summary = str(payload.get("summary") or "").strip() or normalized_summary
    translated_content = str(payload.get("content") or "").strip() or normalized_content

    return {
        "title": translated_title,
        "excerpt": translated_excerpt,
        "summary": translated_summary,
        "content": translated_content,
        "model": GEMINI_FLASH_MODEL,
    }
