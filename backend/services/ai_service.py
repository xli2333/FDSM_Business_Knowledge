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


EDITORIAL_SUMMARY_MIN_CHARS = 200
EDITORIAL_SUMMARY_MAX_CHARS = 500
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
    *,
    body_max_chars: int,
) -> str:
    label_value = _repair_editorial_summary_artifacts(str(label or "").strip()).rstrip("：:")
    if not label_value:
        label_value = EDITORIAL_SUMMARY_DEFAULT_BULLET_LABELS[index % len(EDITORIAL_SUMMARY_DEFAULT_BULLET_LABELS)]
    normalized_body = _truncate_editorial_summary_text(body, max_chars=body_max_chars)
    normalized_body = re.sub(rf"^{re.escape(label_value)}{_EDITORIAL_SUMMARY_COLON_PATTERN}\s*", "", normalized_body).strip()
    return f"- **{label_value}\uff1a** {normalized_body}"


def _build_editorial_summary_intro(
    sentences: list[str],
    *,
    target_min_chars: int = 90,
    max_chars: int = 160,
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
    intro_paragraph = _truncate_editorial_summary_text("".join(intro_parts), max_chars=max_chars)
    return _ensure_editorial_summary_emphasis(intro_paragraph), remaining


def _render_editorial_summary(
    intro_paragraph: str,
    selected_bullets: list[tuple[str | None, str]],
    trailing_paragraph: str,
    *,
    bullet_body_max_chars: int,
) -> str:
    parts: list[str] = []
    if intro_paragraph:
        parts.append(intro_paragraph)
    if selected_bullets:
        bullet_lines = [
            _format_editorial_summary_bullet(label, body, index, body_max_chars=bullet_body_max_chars)
            for index, (label, body) in enumerate(selected_bullets)
        ]
        parts.append("\n".join(bullet_lines))
    if trailing_paragraph:
        parts.append(_ensure_editorial_summary_emphasis(trailing_paragraph))
    return "\n\n".join(part for part in parts if part).strip()


def _compose_editorial_summary_hybrid(
    intro_sentences: list[str],
    remaining_sentences: list[str],
    bullet_items: list[tuple[str | None, str]],
    *,
    min_chars: int,
    max_chars: int,
) -> str:
    intro_pool = [*intro_sentences, *remaining_sentences]
    if not intro_pool and bullet_items:
        intro_pool = _split_editorial_summary_sentences(" ".join(body for _, body in bullet_items[:2]))
    intro_paragraph, leftover_sentences = _build_editorial_summary_intro(intro_pool)

    bullet_seed = list(bullet_items)
    bullet_seed.extend((None, sentence) for sentence in leftover_sentences)
    if len(bullet_seed) >= EDITORIAL_SUMMARY_MAX_BULLETS:
        bullet_target = EDITORIAL_SUMMARY_MAX_BULLETS
    elif len(bullet_seed) >= EDITORIAL_SUMMARY_MIN_BULLETS:
        bullet_target = EDITORIAL_SUMMARY_MIN_BULLETS
    elif bullet_seed:
        bullet_target = min(2, len(bullet_seed))
    else:
        bullet_target = 0
    bullet_body_max_chars = 72 if bullet_target >= 4 else 88

    selected_bullets = bullet_seed[:bullet_target]
    unused_bullets = bullet_seed[bullet_target:]
    trailing_paragraph = ""
    summary = _render_editorial_summary(
        intro_paragraph,
        selected_bullets,
        trailing_paragraph,
        bullet_body_max_chars=bullet_body_max_chars,
    )

    while editorial_summary_visible_length(summary) < min_chars and unused_bullets and len(selected_bullets) < EDITORIAL_SUMMARY_MAX_BULLETS:
        selected_bullets.append(unused_bullets.pop(0))
        bullet_body_max_chars = 72 if len(selected_bullets) >= 4 else 88
        summary = _render_editorial_summary(
            intro_paragraph,
            selected_bullets,
            trailing_paragraph,
            bullet_body_max_chars=bullet_body_max_chars,
        )

    if editorial_summary_visible_length(summary) < min_chars and unused_bullets:
        trailing_paragraph = _truncate_editorial_summary_text(
            "".join(body for _, body in unused_bullets),
            max_chars=min(120, max_chars // 3),
        )
        summary = _render_editorial_summary(
            intro_paragraph,
            selected_bullets,
            trailing_paragraph,
            bullet_body_max_chars=bullet_body_max_chars,
        )

    while editorial_summary_visible_length(summary) > max_chars and trailing_paragraph:
        trailing_length = editorial_summary_visible_length(trailing_paragraph)
        if trailing_length <= 50:
            trailing_paragraph = ""
        else:
            trailing_paragraph = _truncate_editorial_summary_text(trailing_paragraph, max_chars=trailing_length - 20)
        summary = _render_editorial_summary(
            intro_paragraph,
            selected_bullets,
            trailing_paragraph,
            bullet_body_max_chars=bullet_body_max_chars,
        )

    while editorial_summary_visible_length(summary) > max_chars and len(selected_bullets) > EDITORIAL_SUMMARY_MIN_BULLETS:
        selected_bullets.pop()
        bullet_body_max_chars = 72 if len(selected_bullets) >= 4 else 88
        summary = _render_editorial_summary(
            intro_paragraph,
            selected_bullets,
            trailing_paragraph,
            bullet_body_max_chars=bullet_body_max_chars,
        )

    while editorial_summary_visible_length(summary) > max_chars and selected_bullets:
        label, body = selected_bullets[-1]
        body_length = editorial_summary_visible_length(body)
        if body_length <= 40:
            break
        selected_bullets[-1] = (label, _truncate_editorial_summary_text(body, max_chars=body_length - 18))
        summary = _render_editorial_summary(
            intro_paragraph,
            selected_bullets,
            trailing_paragraph,
            bullet_body_max_chars=bullet_body_max_chars,
        )

    if editorial_summary_visible_length(summary) > max_chars:
        intro_budget = max(80, max_chars - sum(editorial_summary_visible_length(body) + 10 for _, body in selected_bullets))
        intro_paragraph = _ensure_editorial_summary_emphasis(
            _truncate_editorial_summary_text(intro_paragraph, max_chars=intro_budget)
        )
        summary = _render_editorial_summary(
            intro_paragraph,
            selected_bullets,
            trailing_paragraph,
            bullet_body_max_chars=bullet_body_max_chars,
        )

    if "**" not in summary:
        if intro_paragraph:
            intro_paragraph = _ensure_editorial_summary_emphasis(intro_paragraph)
        elif trailing_paragraph:
            trailing_paragraph = _ensure_editorial_summary_emphasis(trailing_paragraph)
        summary = _render_editorial_summary(
            intro_paragraph,
            selected_bullets,
            trailing_paragraph,
            bullet_body_max_chars=bullet_body_max_chars,
        )
    return _repair_editorial_summary_artifacts(summary).strip()


def normalize_editorial_summary_output(
    text: str,
    *,
    min_chars: int = EDITORIAL_SUMMARY_MIN_CHARS,
    max_chars: int = EDITORIAL_SUMMARY_MAX_CHARS,
) -> str:
    lines = _repair_editorial_summary_artifacts(str(text or "").replace("\r\n", "\n").replace("\r", "\n")).split("\n")
    paragraph_lines: list[str] = []
    bullet_items: list[tuple[str | None, str]] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue

        was_heading = bool(_EDITORIAL_SUMMARY_HEADING_PREFIX_RE.match(stripped))
        was_list = bool(_EDITORIAL_SUMMARY_LIST_PREFIX_RE.match(stripped))
        normalized_raw = _EDITORIAL_SUMMARY_HEADING_PREFIX_RE.sub("", stripped)
        normalized_raw = _EDITORIAL_SUMMARY_LIST_PREFIX_RE.sub("", normalized_raw)
        plain = _repair_editorial_summary_artifacts(_strip_inline_markdown_tokens(normalized_raw))
        if not paragraph_lines and not bullet_items:
            normalized_raw = _strip_editorial_summary_meta_lead(normalized_raw)
            plain = _strip_editorial_summary_meta_lead(plain)
        if not plain:
            continue
        if _EDITORIAL_SUMMARY_GENERIC_LINE_RE.match(plain):
            continue
        if was_heading:
            continue
        if not paragraph_lines and not bullet_items and _looks_like_editorial_summary_heading(plain):
            continue

        label, body = _extract_editorial_summary_label(normalized_raw)
        if was_list:
            if body:
                bullet_items.append((label, body))
            continue
        if label and editorial_summary_visible_length(body) >= 18:
            bullet_items.append((label, body))
            continue

        plain = re.sub(r"\s+", " ", plain).strip()
        if plain:
            paragraph_lines.append(plain)

    paragraph_sentences = _split_editorial_summary_sentences(" ".join(paragraph_lines))
    if not paragraph_sentences and not bullet_items:
        return ""

    intro_sentences: list[str] = []
    while paragraph_sentences and len(intro_sentences) < 2:
        intro_sentences.append(paragraph_sentences.pop(0))

    return _compose_editorial_summary_hybrid(
        intro_sentences,
        paragraph_sentences,
        bullet_items,
        min_chars=min_chars,
        max_chars=max_chars,
    ).strip()


def build_extractive_summary(content: str) -> str:
    paragraphs = [part.strip() for part in str(content or "").splitlines() if part.strip()]
    if not paragraphs:
        return "No summary is available yet."
    fallback = ""
    for limit in (10, 16, 24):
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
    content_window = _build_editorial_content_window(content, max_chars=18000, tail_chars=4000)
    if not is_ai_enabled():
        return {"summary": fallback, "model": "extractive-fallback"}
    prompt = (
        "You are an editor for a Chinese business knowledge product.\n"
        "Write a concise hybrid-structure article summary.\n"
        "Hard requirements:\n"
        "1. Return the summary body only.\n"
        "2. Keep the total length between 200 and 500 Chinese characters.\n"
        "3. Prefer one short opening paragraph, then use 3 or 4 Markdown bullet points when bullets help readability.\n"
        "4. Do not let the entire answer become only a bullet list.\n"
        "5. Keep 1 to 3 key phrases visibly emphasized with Markdown bold.\n"
        "6. Do not add any prefatory phrases such as 'Below is', 'Here is', '以下是', '下面是', '本文', or '这篇文章'.\n"
        "7. Do not write a title, heading, numbered outline, section label, digest framing, or brief framing.\n"
        "8. Preserve the article's core facts, logic, and implications without inventing anything.\n"
        "9. Use the same language as the article.\n"
        "10. Output Markdown only.\n\n"
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
