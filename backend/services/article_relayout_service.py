from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from backend.services.html_renderer import strip_markdown

RELAYOUT_MODEL = "gemini-3-flash-preview"
RELAYOUT_TEMPLATE = "fudan-business-knowledge-relayout-v1"

FUDAN_RELAYOUT_STYLE_NOTE = (
    "Use the existing Fudan Business Knowledge WeChat template rhythm: academic-business tone, "
    "generous white space, restrained metadata, clean section hierarchy, and no flashy layout gimmicks."
)

_ZH_META_PREFIXES = (
    "导读",
    "来源",
    "出品",
    "作者",
    "编辑",
    "设计",
    "排版",
    "审校",
    "记者",
    "摄影",
)

_EN_META_PREFIXES = (
    "guide",
    "source",
    "produced by",
    "author",
    "editor",
    "design",
    "layout",
    "reviewer",
    "reporter",
    "photo",
)

_ZH_PROMOTIONAL_HARD_PATTERNS = [
    r"点个赞",
    r"关注公众号",
    r"欢迎报名",
    r"火热报名",
    r"报名中",
    r"投票赢",
    r"免费试读",
    r"优惠征订",
    r"后台留言",
    r"转载请",
    r"加入社群",
    r"训练营",
    r"大师课",
    r"直播预告",
]

_ZH_PROMOTIONAL_SOFT_PATTERNS = [
    r"点赞",
    r"转发",
    r"扫码",
    r"订阅",
]

_EN_PROMOTIONAL_HARD_PATTERNS = [
    r"give it a like",
    r"scan the qr",
    r"subscribe",
    r"follow our official",
    r"for reprints",
    r"leave a message in the backend",
    r"register now",
    r"vote to win",
    r"free trial",
    r"join (?:the )?community",
    r"training camp",
    r"masterclass",
]

_EN_PROMOTIONAL_SOFT_PATTERNS = [
    r"share it",
]

_TECHNICAL_PLACEHOLDER_PATTERNS = [
    r"此页面触发全局图片搜索模式",
    r"共找到\s*\d+\s*张图片",
    r"原文正文.*仅包含",
    r"请补充完整.*正文",
    r"无法根据.*正文",
    r"重要提示",
    r"triggered a global image search mode",
    r"a total of \d+ image",
    r"only contains .*article content",
    r"please provide the full article body",
    r"i cannot .* actual article content",
    r"important reminder",
]

_SUMMARY_PLACEHOLDER_PATTERNS = _TECHNICAL_PLACEHOLDER_PATTERNS + [
    r"^#\s*$",
    r"^##\s*$",
    r"^-\s*$",
]


def normalize_newlines(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def clean_model_fence(text: str) -> str:
    cleaned = normalize_newlines(text).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def split_blocks(text: str) -> list[str]:
    normalized = normalize_newlines(text)
    return [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]


def _meta_prefixes(language: str) -> tuple[str, ...]:
    return _EN_META_PREFIXES if language.lower().startswith("en") else _ZH_META_PREFIXES


def looks_like_preserved_meta(block: str, language: str) -> bool:
    lowered = clean_model_fence(block).strip().lower()
    if not lowered:
        return False
    for prefix in _meta_prefixes(language):
        if lowered.startswith(prefix):
            return True
        if lowered.startswith(f"**{prefix}"):
            return True
        if lowered.startswith(f">{prefix}"):
            return True
    return False


def _matches_any(block: str, patterns: list[str]) -> bool:
    lowered = clean_model_fence(block).strip().lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)


def looks_like_promotional_block(block: str, language: str) -> bool:
    normalized = clean_model_fence(block).strip()
    if not normalized:
        return False

    if language.lower().startswith("en"):
        hard_patterns = _EN_PROMOTIONAL_HARD_PATTERNS
        soft_patterns = _EN_PROMOTIONAL_SOFT_PATTERNS
        cta_prefixes = ("subscribe", "follow", "scan", "share", "register", "join", "for reprints")
    else:
        hard_patterns = _ZH_PROMOTIONAL_HARD_PATTERNS
        soft_patterns = _ZH_PROMOTIONAL_SOFT_PATTERNS
        cta_prefixes = ("关注公众号", "扫码", "订阅", "转发", "点赞", "欢迎报名", "后台留言", "转载请")

    lowered = normalized.lower()
    hard_hits = sum(1 for pattern in hard_patterns if re.search(pattern, lowered, flags=re.IGNORECASE))
    soft_hits = sum(1 for pattern in soft_patterns if re.search(pattern, lowered, flags=re.IGNORECASE))
    plain = strip_markdown(normalized)
    compact_length = len(plain)
    starts_like_cta = lowered.startswith(cta_prefixes)

    if hard_hits >= 1 and (compact_length <= 1200 or starts_like_cta):
        return True
    if compact_length <= 280 and soft_hits >= 2:
        return True
    if compact_length <= 180 and (soft_hits >= 1 or starts_like_cta):
        return True
    return False


def looks_like_placeholder_block(block: str) -> bool:
    return _matches_any(block, _TECHNICAL_PLACEHOLDER_PATTERNS)


def strip_irrelevant_tail_blocks(text: str, language: str) -> str:
    blocks = split_blocks(text)
    if not blocks:
        return ""

    kept = list(blocks)
    while kept:
        candidate = kept[-1]
        if looks_like_preserved_meta(candidate, language):
            break
        if looks_like_promotional_block(candidate, language) or looks_like_placeholder_block(candidate):
            kept.pop()
            continue
        break
    return "\n\n".join(kept).strip()


def remove_placeholder_blocks(text: str, language: str) -> str:
    kept: list[str] = []
    for block in split_blocks(text):
        if looks_like_placeholder_block(block):
            continue
        if looks_like_promotional_block(block, language):
            continue
        kept.append(block)
    return "\n\n".join(kept).strip()


def cleanup_source_tail(text: str, language: str) -> str:
    normalized = clean_model_fence(text)
    trimmed = strip_irrelevant_tail_blocks(normalized, language)
    if trimmed:
        return trimmed
    return normalized


def summary_needs_regeneration(summary: str) -> bool:
    normalized = clean_model_fence(summary)
    if not normalized:
        return True
    if _matches_any(normalized, _SUMMARY_PLACEHOLDER_PATTERNS):
        return True
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if lines and all(re.fullmatch(r"[-*#>\s]+", line) for line in lines[: min(4, len(lines))]):
        return True
    if sum(1 for line in lines if re.fullmatch(r"[-*]\s*", line)) >= 2:
        return True
    return False


def normalize_markdown_output(text: str, language: str, *, remove_h1: bool = False) -> str:
    cleaned = clean_model_fence(text)
    lines = [line.rstrip() for line in normalize_newlines(cleaned).split("\n")]

    normalized_lines: list[str] = []
    blank_pending = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if normalized_lines:
                blank_pending = True
            continue
        if re.fullmatch(r"[-*]\s*", stripped):
            continue
        if blank_pending and normalized_lines[-1] != "":
            normalized_lines.append("")
        normalized_lines.append(line.rstrip())
        blank_pending = False

    normalized = "\n".join(normalized_lines).strip()
    if remove_h1:
        normalized = re.sub(r"^\s*#\s+.+?(?:\n+|$)", "", normalized, count=1)
        normalized = normalized.lstrip()

    normalized = remove_placeholder_blocks(normalized, language)
    normalized = strip_irrelevant_tail_blocks(normalized, language)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized


def parse_json_payload(raw: str) -> dict[str, Any]:
    text = clean_model_fence(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            payload = _extract_relayout_payload(text)
            if payload:
                return payload
            raise ValueError("Model did not return a JSON object.")
        try:
            payload = json.loads(text[first : last + 1])
        except json.JSONDecodeError:
            payload = _extract_relayout_payload(text)
            if payload:
                return payload
            raise
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                payload = item
                break
    if not isinstance(payload, dict):
        raise ValueError("Model JSON root is not an object.")
    return payload


def _decode_jsonish_string(value: str) -> str:
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


def _extract_jsonish_field(text: str, field_name: str, sibling_names: tuple[str, ...]) -> str:
    quoted_pattern = rf'"{re.escape(field_name)}"\s*:\s*"(?P<value>(?:[^"\\]|\\.|[\r\n])*)"'
    match = re.search(quoted_pattern, text, flags=re.MULTILINE | re.DOTALL)
    if match:
        return _decode_jsonish_string(match.group("value").strip())

    sibling_group = "|".join(re.escape(name) for name in sibling_names)
    loose_pattern = (
        rf'"{re.escape(field_name)}"\s*:\s*(?P<value>.*?)(?=,\s*"({sibling_group})"\s*:|\s*\}}\s*$)'
    )
    match = re.search(loose_pattern, text, flags=re.MULTILINE | re.DOTALL)
    if match:
        return clean_model_fence(match.group("value")).strip().strip('"').strip()

    label_pattern = rf"^{re.escape(field_name)}\s*:\s*(?P<value>.+)$"
    match = re.search(label_pattern, text, flags=re.MULTILINE)
    if match:
        return match.group("value").strip()
    return ""


def _extract_relayout_payload(text: str) -> dict[str, str]:
    payload: dict[str, str] = {}
    for field_name, siblings in {
        "summary": ("content",),
        "content": ("summary",),
    }.items():
        value = _extract_jsonish_field(text, field_name, siblings)
        if value:
            payload[field_name] = value
    return payload


def build_zh_relayout_prompt(
    *,
    title: str,
    article_type: str,
    excerpt: str,
    main_topic: str,
    current_summary: str,
    source_body: str,
    regenerate_summary: bool,
) -> str:
    summary_line = (
        "The supplied summary contains placeholders or low-value artifacts. Rebuild a clean summary from the source body."
        if regenerate_summary
        else "Preserve the supplied summary substance and simply relayout it."
    )
    return "\n".join(
        [
            "You are relayouting existing Chinese article assets for a current production site.",
            FUDAN_RELAYOUT_STYLE_NOTE,
            "Hard rules:",
            "- Do not invent facts.",
            "- Do not rewrite the article into a different piece.",
            "- Keep facts, numbers, quotes, company names, and argument order.",
            "- Preserve legitimate metadata such as 导读、来源、出品、作者、编辑、审校 when they belong to the article package.",
            "- Remove only unrelated tail blocks such as ads, registration or voting calls, subscribe or share prompts, QR-code instructions, backend reprint instructions, technical placeholder notes, and model apology text.",
            "- The page title is rendered outside the body, so body content must not start with a top-level # title heading.",
            "- Use Markdown only. No HTML. No code fences.",
            "- When the source body contains periodical or package structure lines such as 第42期, 《管理视野》, 趋势/Trend, 对谈/Executive Perspectives, 专栏/Column, 01/02 item numbers, standalone short subtitles, or 导读 labels, convert them into explicit Markdown hierarchy instead of leaving them as flat plain text.",
            "- Keep independent source paragraphs separated by blank lines. Do not collapse many source lines into one giant paragraph.",
            "- Preserve author, source, interview, and editor lines as metadata paragraphs. Do not accidentally promote them to headings.",
            "- Summary should be concise prose or light heading-based markdown. Do not return a bullet-dump made of * or - list items unless the source absolutely requires list structure.",
            "- Return strict JSON only with keys: summary, content.",
            f"- {summary_line}",
            "",
            f"Article title: {title}",
            f"Article type: {article_type or 'Unknown'}",
            f"Deck or excerpt: {excerpt or 'None'}",
            f"Main topic: {main_topic or 'None'}",
            "",
            "Current summary:",
            current_summary.strip() or "(empty)",
            "",
            "Source article body after basic tail cleanup:",
            source_body.strip() or "(empty)",
        ]
    )

def build_en_relayout_prompt(
    *,
    title: str,
    excerpt: str,
    current_summary: str,
    current_content: str,
    regenerate_summary: bool,
) -> str:
    summary_instruction = (
        "If the supplied English summary contains placeholder artifacts or low-value boilerplate, rebuild a clean summary from the English body."
        if regenerate_summary
        else "Preserve the supplied English summary substance and simply relayout it."
    )
    return "\n".join(
        [
            "You are relayouting existing English article assets for the Fudan Business Knowledge site.",
            "Do not translate from Chinese. Work only on the supplied English assets.",
            FUDAN_RELAYOUT_STYLE_NOTE,
            "Hard rules:",
            "- Do not rewrite the body into a different article.",
            "- Preserve meaning and most source sentences.",
            "- Preserve legitimate metadata such as Guide, Source, Produced by, Author, Editor, Reviewer when they belong to the article package.",
            "- Remove only unrelated tail blocks such as ads, registration or voting calls, subscribe or share prompts, QR-code instructions, backend reprint instructions, technical placeholder notes, and model apology text.",
            "- The page title is rendered outside the body, so content must not start with a standalone # title heading.",
            "- Normalize spacing and heading hierarchy with Markdown only.",
            "- When the English body contains package structure such as Issue lines, section labels, numbered items, standalone short subtitles, or Guide labels, convert them into explicit Markdown headings instead of leaving them as flat plain text.",
            "- Keep independent source paragraphs separated by blank lines. Do not collapse many source lines into one giant paragraph.",
            "- Preserve author, source, interview, and editor lines as metadata paragraphs rather than headings.",
            "- Summary should be concise prose or light heading-based markdown. Do not return a bullet-heavy list unless the source absolutely requires list structure.",
            "- Return strict JSON only with keys: summary, content.",
            f"- {summary_instruction}",
            "",
            f"Current title: {title}",
            f"Current excerpt: {excerpt or 'None'}",
            "",
            "Current summary:",
            current_summary.strip() or "(empty)",
            "",
            "Current body after basic tail cleanup:",
            current_content.strip() or "(empty)",
        ]
    )


def _tokenize_for_comparison(text: str, language: str) -> list[str]:
    plain = strip_markdown(clean_model_fence(text)).lower()
    if language.lower().startswith("en"):
        return re.findall(r"[a-z0-9]+", plain)
    return re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]|[a-z0-9]+", plain)


def compare_relayout_similarity(source: str, candidate: str, language: str) -> dict[str, float]:
    source_tokens = _tokenize_for_comparison(source, language)
    candidate_tokens = _tokenize_for_comparison(candidate, language)
    if not source_tokens:
        return {"coverage": 1.0, "length_ratio": 1.0}

    source_counter = Counter(source_tokens)
    candidate_counter = Counter(candidate_tokens)
    matched = sum(min(count, candidate_counter[token]) for token, count in source_counter.items())
    coverage = matched / max(sum(source_counter.values()), 1)
    length_ratio = len(candidate_tokens) / max(len(source_tokens), 1)
    return {"coverage": coverage, "length_ratio": length_ratio}


def relayout_is_close_enough(source: str, candidate: str, language: str) -> bool:
    metrics = compare_relayout_similarity(source, candidate, language)
    source_size = len(strip_markdown(source))
    if source_size < 120:
        return True
    return metrics["coverage"] >= 0.76 and 0.45 <= metrics["length_ratio"] <= 1.75
