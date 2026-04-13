from __future__ import annotations

import re


_ZH_TAIL_LINE_PATTERNS = [
    re.compile(r"^(编辑|编辑排版|排版|审校|设计|摄影|记者|责编|美编|校对)[：:|｜]"),
    re.compile(r"^都看到这儿啦"),
    re.compile(r"^点个赞"),
    re.compile(r"^转发给"),
    re.compile(r"^扫码"),
    re.compile(r"^扫描.*二维码"),
    re.compile(r"^全年.*征订"),
    re.compile(r"^关注公众号"),
    re.compile(r"^关注我们"),
    re.compile(r"^转载[：:|｜]?"),
    re.compile(r"^请后台留言"),
    re.compile(r"^更多.*敬请期待"),
    re.compile(r"^阅读原文$"),
    re.compile(r"^→?$"),
]

_EN_TAIL_LINE_PATTERNS = [
    re.compile(r"^(editor|layout|design|reviewer|copy editor|photography|photo|reporter)[:|]", re.IGNORECASE),
    re.compile(r"^give it a like", re.IGNORECASE),
    re.compile(r"^share (?:it|this)", re.IGNORECASE),
    re.compile(r"^scan (?:the )?qr", re.IGNORECASE),
    re.compile(r"^subscribe", re.IGNORECASE),
    re.compile(r"^follow (?:our )?(?:official account|newsletter|us)", re.IGNORECASE),
    re.compile(r"^for reprints", re.IGNORECASE),
    re.compile(r"^please leave a message", re.IGNORECASE),
]

_TAIL_BLOCK_SNIPPETS = [
    "点赞",
    "转发",
    "扫码订阅",
    "关注公众号",
    "优惠征订",
    "后台留言",
    "转载",
    "like and share",
    "scan the qr",
    "follow our official",
]

_HEAD_NOISE_LINE_PATTERNS = [
    re.compile(r"^往期精彩文章$"),
    re.compile(r"^请访问$"),
    re.compile(r"^(管理视野|复旦商业知识)$"),
    re.compile(r"^小程序$"),
    re.compile(r"^往期精彩文章\s+请访问\s+(?:管理视野|复旦商业知识)\s+小程序$"),
]

_SECTION_LABEL_RE = re.compile(
    r"^(导读|趋势|新知|实践|治理|展望|对谈|专栏|观点|案例|访谈|问答|圆桌|Trend|Research Highlights|"
    r"Executive Perspectives|Column|Insights|Dialogue|Interview)$",
    flags=re.IGNORECASE,
)
_LEAD_LABEL_RE = re.compile(r"^(导读|lead|guide|editor'?s note|editors' note)[：:\s]*(.+)?$", flags=re.IGNORECASE)
_ISSUE_LINE_RE = re.compile(
    r"^(?:第\s*[0-9一二三四五六七八九十百零]+\s*(?:期|辑|卷|讲|刊|号)|issue\s*\d+|vol(?:ume)?\.?\s*\d+)$",
    flags=re.IGNORECASE,
)
_ATTRIBUTION_START_RE = re.compile(
    r"^(文|作者|原作者|改写者|译者|采访|受访|对谈|专栏|口述|整理|来源|出品方?|本文首发于|转载自|转载自公众号|"
    r"编辑|排版|审校|摄影|记者|撰文|编译)(?:\b|[：:|｜])",
    flags=re.IGNORECASE,
)
_STANDALONE_META_LABEL_RE = re.compile(
    r"^(文|作者|原作者|改写者|译者|采访|受访|口述|整理|来源|编辑|排版|审校|摄影|记者|撰文|编译)$",
    flags=re.IGNORECASE,
)
_SHORT_NUMBER_RE = re.compile(r"^(?:0?\d{1,2}|[一二三四五六七八九十]{1,3})$")
_NUMBERED_MARKDOWN_RE = re.compile(r"^#+\s*(\d+)\s*(.+)?$")
_INLINE_NUMBERED_MARKDOWN_RE = re.compile(r"^#(\d+)\s*(.+)$")
_INLINE_NUMBER_TITLE_RE = re.compile(r"^(0?\d{1,2}|[一二三四五六七八九十]{1,3})[.、\s\-]+(.+)$")
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
_SENTENCE_END_RE = re.compile(r"[。！？?!…]$")
_YEAR_PREFIX_RE = re.compile(r"^\d{4}年")
_PART_HEADING_RE = re.compile(
    r"^(?:part\s*\d+|chapter\s*\d+|section\s*\d+|第\s*[0-9一二三四五六七八九十]+\s*部分|"
    r"第\s*[0-9一二三四五六七八九十]+\s*章|第\s*[0-9一二三四五六七八九十]+\s*节).*$",
    flags=re.IGNORECASE,
)
_QA_QUESTION_RE = re.compile(
    r"^(?:Q\s*\d+|Question\s*\d+|问题\s*\d+|问\s*[0-9一二三四五六七八九十]+)[：:.\s\-].*$",
    flags=re.IGNORECASE,
)
_QA_ANSWER_RE = re.compile(r"^(?:A(?:\s+by)?|Answer|答)[：:.\s].*$", flags=re.IGNORECASE)
_URL_ONLY_RE = re.compile(r"^(?:[🔺▲]\s*)?https?://\S+$", flags=re.IGNORECASE)
_SYMBOL_ONLY_RE = re.compile(r"^[✔✅✳⭐☆●○■□▲△▼▽◆◇➤➡→↓🔻]+$")
_NOISE_LINE_PATTERNS = [
    re.compile(r"^扫描图片二维码订阅"),
    re.compile(r"^扫码订阅"),
    re.compile(r"^扫描.*二维码.*订阅"),
    re.compile(r"^长按.*二维码"),
    re.compile(r"^点击.*原文"),
    re.compile(r"^阅读原文$"),
    re.compile(r"^更多.*敬请期待"),
    re.compile(r"^都看到这儿啦"),
    re.compile(r"^全年.*征订"),
    re.compile(r"^关注公众号"),
    re.compile(r"^转载[：:|｜]?"),
    re.compile(r"^点个赞"),
    re.compile(r"^转发给"),
    re.compile(r"^(编辑|编辑排版|排版|审校|设计|摄影|记者|责编|美编|校对)[：:|｜]"),
    re.compile(r"^[-—–]{3,}$"),
    re.compile(r"^→.*$"),
    re.compile(r"^复旦商业知识$"),
    re.compile(r"^请后台留言$"),
]
_EXTRA_TAIL_LINE_PATTERNS = [
    re.compile(r"^专题[：:|｜]"),
    re.compile(r"^栏目[：:|｜]"),
]
_FIELD_LABEL_RE = re.compile(
    r"^(?P<label>时间|地点|联合主办|主办|协办|承办|支持单位|参会对象|授课语言|参会人数|会议费用|报名方式|"
    r"截止日期|缴费方式|联系我们|会议议程|活动议程|嘉宾介绍|参会福利|来源|作者|译者|访谈对象)"
    r"(?:[：:]\s*(?P<value_colon>.+)|\s+(?P<value_space>.+))?$"
)
_SUMMARY_GENERIC_HEADING_RE = re.compile(r"^(摘要|总结|导读|概览|Overview|Summary|Digest)$", flags=re.IGNORECASE)
_SUMMARY_BOLD_BULLET_RE = re.compile(r"^[*-]\s+\*\*(.+?)\*\*(.*)$")
_SUMMARY_STRONG_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
_INLINE_SPLIT_PATTERNS = [
    (re.compile(r"\s+(Part\s*\d+\b)", flags=re.IGNORECASE), r"\n\1"),
    (re.compile(r"\s+(Q\s*\d+\b)", flags=re.IGNORECASE), r"\n\1"),
    (re.compile(r"\s+(A(?:\s+by)?\b)", flags=re.IGNORECASE), r"\n\1"),
    (
        re.compile(
            r"\s+(时间|地点|联合主办|主办|协办|承办|支持单位|参会对象|授课语言|参会人数|会议费用|报名方式|截止日期|"
            r"缴费方式|联系我们|会议议程|活动议程|嘉宾介绍|参会福利)\s+"
        ),
        r"\n\1 ",
    ),
]


def _normalize_newlines(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _split_blocks(text: str) -> list[str]:
    normalized = _normalize_newlines(text).strip()
    if not normalized:
        return []
    return [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]


def _block_lines(block: str) -> list[str]:
    return [line.strip() for line in _normalize_newlines(block).split("\n") if line.strip()]


def _matches_any(line: str, patterns: list[re.Pattern[str]]) -> bool:
    stripped = str(line or "").strip()
    return any(pattern.search(stripped) for pattern in patterns)


def _is_head_noise_line(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return False
    return _matches_any(stripped, _HEAD_NOISE_LINE_PATTERNS)


def _is_tail_metadata_block(block: str, language: str) -> bool:
    lines = _block_lines(block)
    if not lines:
        return False
    patterns = _EN_TAIL_LINE_PATTERNS if language.lower().startswith("en") else _ZH_TAIL_LINE_PATTERNS
    if all(_matches_any(line, patterns) for line in lines):
        return True
    block_lowered = block.lower()
    if len(lines) <= 6 and any(snippet in block_lowered for snippet in _TAIL_BLOCK_SNIPPETS):
        return True
    return False


def _strip_edge_noise_lines(text: str, language: str) -> str:
    lines = _normalize_newlines(text).split("\n")
    start = 0
    end = len(lines)

    while start < end and (not lines[start].strip() or _is_head_noise_line(lines[start])):
        start += 1

    while end > start and (not lines[end - 1].strip() or _matches_any(lines[end - 1], _EXTRA_TAIL_LINE_PATTERNS)):
        end -= 1

    return "\n".join(lines[start:end]).strip()


def cleanup_display_markdown(text: str, language: str) -> str:
    cleaned_text = _strip_edge_noise_lines(text, language)
    blocks = _split_blocks(cleaned_text)
    if not blocks:
        return ""

    trimmed = list(blocks)
    while trimmed and _is_tail_metadata_block(trimmed[-1], language):
        trimmed.pop()

    output = "\n\n".join(trimmed).strip()
    output = re.sub(r"\n{3,}", "\n\n", output)
    return output.strip()


def _expand_inline_structure_text(text: str) -> str:
    expanded = _normalize_newlines(text)
    for pattern, replacement in _INLINE_SPLIT_PATTERNS:
        expanded = pattern.sub(replacement, expanded)
    return expanded


def normalize_summary_display_markdown(text: str, language: str) -> str:
    cleaned = cleanup_display_markdown(text, language)
    if not cleaned:
        return ""

    lines = _normalize_newlines(cleaned).split("\n")
    normalized_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if normalized_lines and normalized_lines[-1] != "":
                normalized_lines.append("")
            continue

        heading_match = _MARKDOWN_HEADING_RE.match(stripped)
        if heading_match:
            heading_text = heading_match.group(1).strip()
            if _SUMMARY_GENERIC_HEADING_RE.match(heading_text):
                continue
            normalized_lines.append(f"### {heading_text}")
            continue

        strong_heading = _SUMMARY_STRONG_HEADING_RE.match(stripped)
        if strong_heading:
            heading_text = strong_heading.group(1).strip().rstrip("：:")
            if heading_text and not _SUMMARY_GENERIC_HEADING_RE.match(heading_text):
                normalized_lines.append(f"### {heading_text}")
                continue

        bullet_match = _SUMMARY_BOLD_BULLET_RE.match(stripped)
        if bullet_match:
            label = bullet_match.group(1).strip().rstrip("：:")
            tail = bullet_match.group(2).strip()
            split_as_heading = tail.startswith(("：", ":"))
            if split_as_heading:
                tail = tail[1:].strip()
            if label and len(label) <= 40 and split_as_heading:
                normalized_lines.append(f"### {label}")
                if tail:
                    normalized_lines.append(tail)
                continue
            normalized_lines.append(stripped)
            continue

        if re.fullmatch(r"[*-]\s*", stripped):
            continue

        normalized_lines.append(stripped)

    normalized = "\n".join(normalized_lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _is_probable_short_heading(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped or len(stripped) > 42:
        return False
    if re.match(r"^[>*-]\s*", stripped):
        return False
    if _SENTENCE_END_RE.search(stripped):
        return False
    if _SHORT_NUMBER_RE.fullmatch(stripped):
        return True
    if _YEAR_PREFIX_RE.match(stripped):
        return False
    if _URL_ONLY_RE.match(stripped):
        return False
    if re.search(r"[，,；;]", stripped) and len(stripped) > 20:
        return False
    if re.search(r"[《》“”\"A-Za-z]", stripped):
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff\s·、（）()\-]+", stripped))


def _is_noise_line(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return False
    if _SYMBOL_ONLY_RE.fullmatch(stripped):
        return True
    return _matches_any(stripped, _NOISE_LINE_PATTERNS)


def _is_tail_line(line: str, language: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return False
    patterns = list(_NOISE_LINE_PATTERNS) + list(_EXTRA_TAIL_LINE_PATTERNS)
    if language.lower().startswith("en"):
        patterns.extend(_EN_TAIL_LINE_PATTERNS)
    else:
        patterns.extend(_ZH_TAIL_LINE_PATTERNS)
    return _matches_any(stripped, patterns)


def _is_attribution_continuation(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped or len(stripped) > 64:
        return False
    if _SHORT_NUMBER_RE.fullmatch(stripped):
        return False
    if _SECTION_LABEL_RE.match(stripped) or _LEAD_LABEL_RE.match(stripped) or _ATTRIBUTION_START_RE.match(stripped):
        return False
    if _FIELD_LABEL_RE.match(stripped) or _PART_HEADING_RE.match(stripped) or _QA_QUESTION_RE.match(stripped):
        return False
    if _is_noise_line(stripped) or _URL_ONLY_RE.match(stripped):
        return False
    if re.match(r"^[#>*-]", stripped):
        return False
    if _SENTENCE_END_RE.search(stripped):
        return False
    if _YEAR_PREFIX_RE.match(stripped):
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9 ·、（）()《》“”\"，,./&\-]+", stripped))


def _append_block(blocks: list[tuple[str, str]], kind: str, text: str) -> None:
    value = str(text or "").strip()
    if not value:
        return
    if blocks and blocks[-1] == (kind, value):
        return
    blocks.append((kind, value))


def _next_non_empty(lines: list[str], start: int) -> str:
    for item in lines[start:]:
        stripped = item.strip()
        if stripped:
            return stripped
    return ""


def _current_block_kind(blocks: list[tuple[str, str]]) -> str:
    return blocks[-1][0] if blocks else ""


def _is_contextual_heading(line: str, *, previous_kind: str, next_non_empty: str) -> bool:
    stripped = str(line or "").strip()
    if (
        _ISSUE_LINE_RE.match(stripped)
        or _ATTRIBUTION_START_RE.match(stripped)
        or _STANDALONE_META_LABEL_RE.match(stripped)
        or _SECTION_LABEL_RE.match(stripped)
        or _FIELD_LABEL_RE.match(stripped)
        or _PART_HEADING_RE.match(stripped)
        or _QA_QUESTION_RE.match(stripped)
        or _QA_ANSWER_RE.match(stripped)
    ):
        return False
    if _is_noise_line(stripped) or _URL_ONLY_RE.match(stripped) or _YEAR_PREFIX_RE.match(stripped):
        return False
    if not _is_probable_short_heading(stripped):
        return False
    if previous_kind in {"heading", "section", "issue"}:
        return True
    if next_non_empty and _is_probable_short_heading(next_non_empty):
        return True
    return bool(next_non_empty and len(next_non_empty) > 24)


def _is_numbered_heading_title(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped or len(stripped) > 56:
        return False
    if _ATTRIBUTION_START_RE.match(stripped) or _SECTION_LABEL_RE.match(stripped) or _LEAD_LABEL_RE.match(stripped):
        return False
    if _FIELD_LABEL_RE.match(stripped) or _PART_HEADING_RE.match(stripped) or _QA_QUESTION_RE.match(stripped):
        return False
    if _is_noise_line(stripped) or _YEAR_PREFIX_RE.match(stripped):
        return False
    return True


def _is_structural_line(line: str) -> bool:
    stripped = str(line or "").strip()
    return bool(
        _NUMBERED_MARKDOWN_RE.match(stripped)
        or _INLINE_NUMBERED_MARKDOWN_RE.match(stripped)
        or _MARKDOWN_HEADING_RE.match(stripped)
        or _INLINE_NUMBER_TITLE_RE.match(stripped)
        or _ISSUE_LINE_RE.match(stripped)
        or _SECTION_LABEL_RE.match(stripped)
        or _LEAD_LABEL_RE.match(stripped)
        or _ATTRIBUTION_START_RE.match(stripped)
        or _STANDALONE_META_LABEL_RE.match(stripped)
        or _FIELD_LABEL_RE.match(stripped)
        or _PART_HEADING_RE.match(stripped)
        or _QA_QUESTION_RE.match(stripped)
        or _QA_ANSWER_RE.match(stripped)
        or _SHORT_NUMBER_RE.fullmatch(stripped)
        or _URL_ONLY_RE.match(stripped)
        or _is_noise_line(stripped)
    )


def _should_join_paragraph_line(current: str, next_line: str) -> bool:
    current_stripped = str(current or "").strip()
    next_stripped = str(next_line or "").strip()
    if not current_stripped or not next_stripped:
        return False
    if _ISSUE_LINE_RE.match(current_stripped) or _YEAR_PREFIX_RE.match(current_stripped):
        return False
    if _SENTENCE_END_RE.search(current_stripped):
        return False
    if _is_quote_paragraph(next_stripped):
        return False
    if _is_structural_line(next_stripped):
        return False
    return True


def _normalize_lead_label(label: str) -> str:
    lowered = label.lower()
    if lowered in {"lead", "guide", "editor's note", "editors' note"}:
        return "导读"
    return label


def _format_field_line(line: str) -> str | None:
    match = _FIELD_LABEL_RE.match(line.strip())
    if not match:
        return None
    label = match.group("label").strip()
    value = (match.group("value_colon") or match.group("value_space") or "").strip()
    if not value:
        return f"### {label}"
    return f"**{label}：** {value}"


def _is_quote_paragraph(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or len(stripped) > 160:
        return False
    return (
        (stripped.startswith("“") and stripped.endswith("”"))
        or (stripped.startswith('"') and stripped.endswith('"'))
    )


def _split_inline_heading_body(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped:
        return "", ""

    quote_match = re.search(r"([”》\"])\s+(.+)$", stripped)
    if quote_match:
        split_at = quote_match.start(2)
        heading = stripped[:split_at].strip()
        body = stripped[split_at:].strip()
        if 4 <= len(heading) <= 40 and body:
            return heading, body

    year_match = re.search(r"\s+(?=\d{4}年)", stripped)
    if year_match:
        heading = stripped[: year_match.start()].strip()
        body = stripped[year_match.end() :].strip()
        if 4 <= len(heading) <= 40 and body:
            return heading, body

    for match in re.finditer(r"\s+", stripped):
        heading = stripped[: match.start()].strip()
        body = stripped[match.end() :].strip()
        if not (4 <= len(heading) <= 24 and body):
            continue
        if len(body) >= 16 and re.search(r"[，。！？?!]", body[:48]):
            return heading, body

    return stripped, ""


def normalize_article_display_markdown(text: str, language: str) -> str:
    cleaned = cleanup_display_markdown(text, language)
    if not cleaned:
        return ""

    lines = _expand_inline_structure_text(cleaned).split("\n")
    blocks: list[tuple[str, str]] = []
    pending_section_number: str | None = None
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()

        if not stripped:
            index += 1
            continue

        if _is_noise_line(stripped):
            index += 1
            continue

        numbered_heading = _NUMBERED_MARKDOWN_RE.match(stripped)
        if numbered_heading:
            section_number = numbered_heading.group(1)
            heading_text = (numbered_heading.group(2) or "").strip()
            if heading_text:
                _append_block(blocks, "heading", f"### {section_number}. {heading_text}")
            else:
                pending_section_number = section_number
            index += 1
            continue

        plain_number = _SHORT_NUMBER_RE.fullmatch(stripped)
        if plain_number:
            pending_section_number = str(int(stripped)) if stripped.isdigit() else stripped
            index += 1
            continue

        inline_number_title = _INLINE_NUMBER_TITLE_RE.match(stripped)
        if inline_number_title:
            number = inline_number_title.group(1)
            cleaned_number = number.lstrip("0") or number
            heading_text, remainder = _split_inline_heading_body(inline_number_title.group(2).strip())
            _append_block(blocks, "heading", f"### {cleaned_number}. {heading_text}")
            if remainder:
                _append_block(blocks, "paragraph", remainder)
            index += 1
            continue

        next_non_empty = _next_non_empty(lines, index + 1)
        previous_kind = _current_block_kind(blocks)

        if _ISSUE_LINE_RE.match(stripped):
            _append_block(blocks, "issue", f"### {stripped}")
            index += 1
            continue

        if pending_section_number and _is_numbered_heading_title(stripped):
            _append_block(blocks, "heading", f"### {pending_section_number}. {stripped}")
            pending_section_number = None
            index += 1
            continue
        pending_section_number = None

        inline_numbered_heading = _INLINE_NUMBERED_MARKDOWN_RE.match(stripped)
        if inline_numbered_heading:
            _append_block(blocks, "heading", f"### {inline_numbered_heading.group(1)}. {inline_numbered_heading.group(2).strip()}")
            index += 1
            continue

        markdown_heading = _MARKDOWN_HEADING_RE.match(stripped)
        if markdown_heading:
            _append_block(blocks, "heading", f"### {markdown_heading.group(1).strip()}")
            index += 1
            continue

        if _SECTION_LABEL_RE.match(stripped):
            _append_block(blocks, "section", f"### {stripped}")
            index += 1
            continue

        field_line = _format_field_line(stripped)
        if field_line:
            kind = "heading" if field_line.startswith("### ") else "meta"
            _append_block(blocks, kind, field_line)
            index += 1
            continue

        if _PART_HEADING_RE.match(stripped) or _QA_QUESTION_RE.match(stripped):
            _append_block(blocks, "heading", f"### {stripped}")
            index += 1
            continue

        if _QA_ANSWER_RE.match(stripped):
            _append_block(blocks, "meta", f"**{stripped}**")
            index += 1
            continue

        lead_match = _LEAD_LABEL_RE.match(stripped)
        if lead_match:
            label = _normalize_lead_label(lead_match.group(1))
            tail = (lead_match.group(2) or "").strip()
            if tail:
                _append_block(blocks, "meta", f"**{label}：** {tail}")
            else:
                _append_block(blocks, "meta", f"**{label}：**")
            index += 1
            continue

        if _ATTRIBUTION_START_RE.match(stripped) or _STANDALONE_META_LABEL_RE.match(stripped):
            meta_parts = [stripped]
            while index + 1 < len(lines):
                continuation = lines[index + 1].strip()
                if not _is_attribution_continuation(continuation):
                    break
                meta_parts.append(continuation)
                index += 1
            if len(meta_parts) >= 2 and _STANDALONE_META_LABEL_RE.match(meta_parts[0]):
                _append_block(blocks, "meta", f"{meta_parts[0]} | {' '.join(meta_parts[1:])}")
            else:
                _append_block(blocks, "meta", " ".join(meta_parts))
            index += 1
            continue

        if _is_contextual_heading(stripped, previous_kind=previous_kind, next_non_empty=next_non_empty):
            heading_text, remainder = _split_inline_heading_body(stripped)
            _append_block(blocks, "heading", f"### {heading_text}")
            if remainder:
                _append_block(blocks, "paragraph", remainder)
            index += 1
            continue

        if _URL_ONLY_RE.match(stripped):
            _append_block(blocks, "paragraph", stripped)
            index += 1
            continue

        paragraph = stripped
        while index + 1 < len(lines):
            continuation = lines[index + 1].strip()
            if not continuation or not _should_join_paragraph_line(paragraph, continuation):
                break
            paragraph = f"{paragraph} {continuation}"
            index += 1
        if _is_quote_paragraph(paragraph):
            _append_block(blocks, "blockquote", f"> {paragraph}")
        else:
            _append_block(blocks, "paragraph", paragraph)
        index += 1

    while blocks:
        tail_lines = [line.strip() for line in blocks[-1][1].split("\n") if line.strip()]
        if not tail_lines:
            blocks.pop()
            continue
        if all(_is_tail_line(line, language) for line in tail_lines):
            blocks.pop()
            continue
        break

    normalized = "\n\n".join(text for _, text in blocks).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _structure_marker_count(markdown: str) -> int:
    lines = [line.strip() for line in _normalize_newlines(markdown).split("\n") if line.strip()]
    markers = 0
    for line in lines:
        if _MARKDOWN_HEADING_RE.match(line):
            markers += 1
            continue
        if _INLINE_NUMBERED_MARKDOWN_RE.match(line):
            markers += 1
            continue
        if _SHORT_NUMBER_RE.fullmatch(line):
            markers += 1
            continue
        if (
            _SECTION_LABEL_RE.match(line)
            or _ATTRIBUTION_START_RE.match(line)
            or _LEAD_LABEL_RE.match(line)
            or _PART_HEADING_RE.match(line)
            or _QA_QUESTION_RE.match(line)
        ):
            markers += 1
            continue
        if _is_probable_short_heading(line):
            markers += 1
    return markers


def stored_html_needs_rerender(stored_html: str, content_markdown: str) -> bool:
    html = str(stored_html or "").strip()
    markdown = str(content_markdown or "").strip()
    if not html or not markdown:
        return False

    if re.search(r"(?:^|[>\s])#\d+", html):
        return True
    if re.search(r"(?:^|[>\s])#\s+\S", html):
        return True

    paragraph_count = len(re.findall(r"<p\b", html, flags=re.IGNORECASE))
    heading_count = len(re.findall(r"<h[1-6]\b", html, flags=re.IGNORECASE))
    if paragraph_count <= 5 and heading_count == 0 and _structure_marker_count(markdown) >= 6:
        return True
    return False
