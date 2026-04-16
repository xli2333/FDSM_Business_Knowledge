from __future__ import annotations

import re


def _marker_pair_score(positions: list[int]) -> int:
    score = 0
    for index in range(0, len(positions), 2):
        if index + 1 < len(positions):
            score += positions[index + 1] - positions[index]
    return score


def _remove_most_likely_unmatched_marker(text: str, marker: str) -> str:
    pattern = re.escape(marker)
    positions = [match.start() for match in re.finditer(pattern, text)]
    if not positions or len(positions) % 2 == 0:
        return text
    if len(positions) == 1:
        index = positions[0]
        return text[:index] + text[index + len(marker) :]
    drop_first_score = _marker_pair_score(positions[1:])
    drop_last_score = _marker_pair_score(positions[:-1])
    index = positions[0] if drop_first_score <= drop_last_score else positions[-1]
    return text[:index] + text[index + len(marker) :]


def _single_marker_positions(text: str) -> list[int]:
    positions: list[int] = []
    for index, character in enumerate(text):
        if character != "*":
            continue
        if index > 0 and text[index - 1] == "*":
            continue
        if index + 1 < len(text) and text[index + 1] == "*":
            continue
        prefix = text[:index]
        if (not prefix.strip() or re.fullmatch(r"[\s>]+", prefix or "")) and index + 1 < len(text) and text[index + 1] == " ":
            continue
        positions.append(index)
    return positions


def _remove_most_likely_unmatched_single_marker(text: str) -> str:
    positions = _single_marker_positions(text)
    if not positions or len(positions) % 2 == 0:
        return text
    if len(positions) == 1:
        index = positions[0]
        return text[:index] + text[index + 1 :]
    drop_first_score = _marker_pair_score(positions[1:])
    drop_last_score = _marker_pair_score(positions[:-1])
    index = positions[0] if drop_first_score <= drop_last_score else positions[-1]
    return text[:index] + text[index + 1 :]


def _repair_chat_markdown_line(text: str) -> str:
    line = str(text or "")
    line = re.sub(r"\*\*\*([^*\n]+?)\*\*", r"**\1**", line)
    line = re.sub(r"\*\*(?=[^\s*])([^*\n]*?[^\s*])\*(?!\*)", r"**\1**", line)
    line = re.sub(r"(^|[^\*])\*(?=[^\s*])([^*\n]*?[^\s*])\*\*", r"\1**\2**", line)
    line = re.sub(
        r"(^|[\s\u3400-\u9fff\u3000-\u303f\uff00-\uffef])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?=$|[\s\u3400-\u9fff\u3000-\u303f\uff00-\uffef])",
        r"\1**\2**",
        line,
    )
    line = re.sub(r"(^|(?:\s|[>•\-])\s*)\*([^*\n]{1,40}?[：:])\*(?=\s|$)", r"\1**\2**", line)
    line = re.sub(r"(^|(?:\s|[>•\-])\s*)\*([^*\n]{1,40}?[：:])(?=\s|$)", r"\1**\2**", line)
    line = re.sub(r"\*\*([^*\n]*?[\)）\]】》」』”’])\*\*(?=[\u3400-\u9fffA-Za-z0-9])", r"**\1** ", line)
    line = _remove_most_likely_unmatched_single_marker(line)
    line = _remove_most_likely_unmatched_marker(line, "**")
    return line


def _is_markdown_table_separator_line(text: str) -> bool:
    line = str(text or "").strip()
    if "-" not in line:
        return False
    return bool(re.match(r"^\|?[\s:-]+(?:\|[\s:-]+)+\|?$", line))


def _is_markdown_table_row_line(text: str) -> bool:
    line = str(text or "").strip()
    if "|" not in line:
        return False
    segments = [segment.strip() for segment in line.split("|")]
    meaningful_segments = [segment for segment in segments if segment]
    return len(meaningful_segments) >= 2


def _normalize_markdown_tables(text: str) -> str:
    input_lines = str(text or "").split("\n")
    output_lines: list[str] = []
    index = 0

    while index < len(input_lines):
        current_line = input_lines[index]
        next_line = input_lines[index + 1] if index + 1 < len(input_lines) else ""
        is_table_header = _is_markdown_table_row_line(current_line) and _is_markdown_table_separator_line(next_line)

        if not is_table_header:
            output_lines.append(current_line)
            index += 1
            continue

        if output_lines and output_lines[-1].strip():
            output_lines.append("")

        output_lines.append(current_line.rstrip())
        index += 1

        while index < len(input_lines) and (
            _is_markdown_table_separator_line(input_lines[index]) or _is_markdown_table_row_line(input_lines[index])
        ):
            output_lines.append(str(input_lines[index] or "").rstrip())
            index += 1

        if index < len(input_lines) and str(input_lines[index] or "").strip():
            output_lines.append("")

    return "\n".join(output_lines)


def _strip_inline_citation_markers(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"\[\^\d+\]", "", value)
    value = re.sub(r"(?:\[(?:\d{1,3})\]){1,8}", "", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def normalize_chat_answer_markdown(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    for _ in range(2):
        repaired = "\n".join(_repair_chat_markdown_line(raw_line) for raw_line in value.split("\n"))
        if repaired == value:
            break
        value = repaired
    value = _normalize_markdown_tables(value)
    value = _strip_inline_citation_markers(value)
    return value.strip()
