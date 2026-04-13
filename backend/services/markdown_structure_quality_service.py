from __future__ import annotations

import re


_ISSUE_LINE_RE = re.compile(
    r"^(?:第\s*[0-9一二三四五六七八九十百零]+\s*(?:期|辑|卷|讲|刊|号)|issue\s*\d+|vol(?:ume)?\.?\s*\d+)$",
    flags=re.IGNORECASE,
)
_SECTION_LABEL_RE = re.compile(
    r"^(导读|趋势|新知|实践|治理|展望|对谈|专栏|观点|案例|访谈|问答|圆桌|Trend|Research Highlights|"
    r"Executive Perspectives|Column|Insights|Dialogue|Interview)$",
    flags=re.IGNORECASE,
)
_NUMBER_LINE_RE = re.compile(r"^(?:0?\d{1,2}|[一二三四五六七八九十]{1,3})$")
_INLINE_NUMBER_TITLE_RE = re.compile(r"^(0?\d{1,2}|[一二三四五六七八九十]{1,3})[.、\s\-]+(.+)$")
_PART_HEADING_RE = re.compile(
    r"^(?:part\s*\d+|chapter\s*\d+|section\s*\d+|第\s*[0-9一二三四五六七八九十]+\s*部分|"
    r"第\s*[0-9一二三四五六七八九十]+\s*章|第\s*[0-9一二三四五六七八九十]+\s*节).*$",
    flags=re.IGNORECASE,
)
_QA_QUESTION_RE = re.compile(
    r"^(?:Q\s*\d+|Question\s*\d+|问题\s*\d+|问\s*[0-9一二三四五六七八九十]+)[：:.\s\-].*$",
    flags=re.IGNORECASE,
)
_ATTRIBUTION_START_RE = re.compile(
    r"^(文|作者|原作者|改写者|译者|采访|受访|对谈|专栏|口述|整理|来源|出品方?|本文首发于|转载自|转载自公众号|"
    r"编辑|排版|审校|摄影|记者|撰文|编译)(?:\b|[：:|｜])",
    flags=re.IGNORECASE,
)
_MARKDOWN_HEADING_RE = re.compile(r"^#{2,6}\s+\S")
_LEAD_MARKER_RE = re.compile(r"^\*\*(导读|Guide|Lead|Editor's Note|Editors' Note)[：:]\*\*", flags=re.IGNORECASE)
_STRONG_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
_SPEAKER_LINE_RE = re.compile(r"^\*\*[^*]{1,24}[：:]\*\*(?:\s+\S.*)?$")
_BLOCKQUOTE_RE = re.compile(r"^>\s+\S")
_SUMMARY_BULLET_RE = re.compile(r"^(?:[*-]\s+\*\*|[*-]\s{2,}\*\*)")


def _normalize_newlines(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in _normalize_newlines(text).split("\n") if line.strip()]


def _is_short_heading_like(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped or len(stripped) > 42:
        return False
    if _ISSUE_LINE_RE.match(stripped) or _SECTION_LABEL_RE.match(stripped) or _NUMBER_LINE_RE.match(stripped):
        return True
    if _INLINE_NUMBER_TITLE_RE.match(stripped) or _PART_HEADING_RE.match(stripped) or _QA_QUESTION_RE.match(stripped):
        return True
    if _ATTRIBUTION_START_RE.match(stripped):
        return False
    if re.search(r"[。！？?!…]$", stripped):
        return False
    if re.search(r"[《》“”\"A-Za-z]", stripped):
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff\s·、（）()\-]+", stripped))


def _source_structure_signal_count(source_text: str) -> int:
    lines = _non_empty_lines(source_text)
    signals = 0
    for line in lines:
        if (
            _ISSUE_LINE_RE.match(line)
            or _SECTION_LABEL_RE.match(line)
            or _NUMBER_LINE_RE.match(line)
            or _INLINE_NUMBER_TITLE_RE.match(line)
            or _PART_HEADING_RE.match(line)
            or _QA_QUESTION_RE.match(line)
        ):
            signals += 1
            continue
        if _ATTRIBUTION_START_RE.match(line):
            signals += 1
            continue
        if _is_short_heading_like(line):
            signals += 1
    return signals


def _markdown_structure_count(markdown_text: str) -> int:
    lines = _non_empty_lines(markdown_text)
    count = 0
    for line in lines:
        if _MARKDOWN_HEADING_RE.match(line):
            count += 1
            continue
        if _LEAD_MARKER_RE.match(line):
            count += 1
            continue
        if _STRONG_HEADING_RE.match(line):
            count += 1
            continue
        if _SPEAKER_LINE_RE.match(line):
            count += 1
            continue
        if _BLOCKQUOTE_RE.match(line):
            count += 1
    return count


def markdown_structure_quality_signals(
    *,
    source_text: str,
    formatted_markdown: str,
    summary_text: str,
) -> dict[str, object]:
    source_lines = _non_empty_lines(source_text)
    markdown_lines = _non_empty_lines(formatted_markdown)
    source_signal_count = _source_structure_signal_count(source_text)
    markdown_structure_count = _markdown_structure_count(formatted_markdown)
    leading_lines_match = False
    if source_lines and markdown_lines:
        source_head = "\n".join(source_lines[:8])
        markdown_head = "\n".join(markdown_lines[:8])
        leading_lines_match = source_head == markdown_head

    summary_lines = _non_empty_lines(summary_text)
    bullet_summary = bool(summary_lines and _SUMMARY_BULLET_RE.match(summary_lines[0]))

    reasons: list[str] = []
    if source_signal_count >= 8 and markdown_structure_count <= 1:
        reasons.append("source_has_strong_structure_but_markdown_has_too_few_headings")
    if source_signal_count >= 12 and markdown_structure_count * 3 < source_signal_count:
        reasons.append("source_structure_signals_far_exceed_markdown_structure")
    if source_signal_count >= 8 and leading_lines_match and markdown_structure_count <= 2:
        reasons.append("markdown_head_is_nearly_raw_source_without_relayout")
    if bullet_summary:
        reasons.append("summary_is_bullet_heavy_and_needs_regeneration")

    severe_reasons = {
        "source_has_strong_structure_but_markdown_has_too_few_headings",
        "markdown_head_is_nearly_raw_source_without_relayout",
        "summary_is_bullet_heavy_and_needs_regeneration",
    }
    matched_severe_reasons = [reason for reason in reasons if reason in severe_reasons]
    severity = "none"
    if matched_severe_reasons:
        severity = "severe"
    elif reasons:
        severity = "monitor"

    return {
        "source_signal_count": source_signal_count,
        "markdown_structure_count": markdown_structure_count,
        "leading_lines_match": leading_lines_match,
        "bullet_summary": bullet_summary,
        "severity": severity,
        "needs_rerun": bool(matched_severe_reasons),
        "reasons": reasons,
    }


def markdown_structure_needs_rerun(
    *,
    source_text: str,
    formatted_markdown: str,
    summary_text: str,
) -> bool:
    payload = markdown_structure_quality_signals(
        source_text=source_text,
        formatted_markdown=formatted_markdown,
        summary_text=summary_text,
    )
    return bool(payload["needs_rerun"])
