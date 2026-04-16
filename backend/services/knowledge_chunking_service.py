from __future__ import annotations

import hashlib
import re
from typing import Any

from backend.config import RAG_CHUNK_CHAR_LIMIT, RAG_CHUNK_OVERLAP
from backend.services.article_ai_output_service import build_current_article_source_hash

TEXT_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?；;])")


def normalize_article_text(text: str | None) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def count_visible_tokens(text: str | None) -> int:
    return len(TEXT_TOKEN_PATTERN.findall(str(text or "")))


def build_article_source_hash(article_row: Any) -> str:
    return build_current_article_source_hash(article_row)


def _compact_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_heading(text: str) -> str:
    cleaned = re.sub(r"^#+\s*", "", text).strip()
    cleaned = cleaned.rstrip("：:")
    return _compact_text(cleaned)


def _looks_like_heading(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if raw.startswith("#"):
        return True
    compact = _compact_text(raw)
    if len(compact) > 36:
        return False
    if re.search(r"[。！？!?]", compact):
        return False
    if compact.endswith(("：", ":")):
        return True
    if compact.startswith(("一、", "二、", "三、", "四、", "五、", "1.", "2.", "3.", "4.")):
        return True
    return len(compact) <= 18


def _paragraphs(text: str) -> list[str]:
    normalized = normalize_article_text(text)
    if not normalized:
        return []
    blocks = [item.strip() for item in re.split(r"\n\s*\n", normalized) if item.strip()]
    paragraphs: list[str] = []
    for block in blocks:
        lines = [_compact_text(line) for line in block.split("\n") if _compact_text(line)]
        if not lines:
            continue
        if len(lines) == 1:
            paragraphs.append(lines[0])
            continue
        merged = " ".join(lines)
        paragraphs.append(_compact_text(merged))
    return paragraphs


def _split_long_paragraph(text: str, *, char_limit: int, overlap: int) -> list[str]:
    paragraph = _compact_text(text)
    if len(paragraph) <= char_limit:
        return [paragraph]
    sentences = [item.strip() for item in SENTENCE_SPLIT_PATTERN.split(paragraph) if item.strip()]
    if len(sentences) <= 1:
        step = max(char_limit - max(0, overlap), 200)
        return [paragraph[index : index + char_limit].strip() for index in range(0, len(paragraph), step) if paragraph[index : index + char_limit].strip()]

    segments: list[str] = []
    buffer = ""
    for sentence in sentences:
        candidate = f"{buffer}{sentence}".strip()
        if buffer and len(candidate) > char_limit:
            segments.append(buffer.strip())
            tail = buffer[-overlap:].strip() if overlap > 0 else ""
            buffer = f"{tail}{sentence}".strip() if tail else sentence
            continue
        buffer = candidate
    if buffer.strip():
        segments.append(buffer.strip())
    return segments


def _overlap_prefix(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return ""
    return text[-overlap:].strip()


def _build_search_text(article: dict[str, Any], heading: str | None, content: str) -> str:
    parts = [
        str(article.get("title") or "").strip(),
        str(article.get("main_topic") or "").strip(),
        str(article.get("tag_text") or "").strip(),
        str(article.get("excerpt") or "").strip(),
        str(heading or "").strip(),
        str(content or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def build_article_chunks(
    article_row: Any,
    *,
    char_limit: int = RAG_CHUNK_CHAR_LIMIT,
    overlap: int = RAG_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    article = dict(article_row)
    article_title = str(article.get("title") or "").strip()
    paragraphs = _paragraphs(article.get("content"))
    if not paragraphs:
        return []

    chunks: list[dict[str, Any]] = []
    buffer: list[str] = []
    current_heading = article_title

    def flush_buffer(*, next_seed: str | None = None) -> None:
        nonlocal buffer
        chunk_content = "\n\n".join(item for item in buffer if item).strip()
        if not chunk_content:
            buffer = [next_seed] if next_seed else []
            return
        chunk_index = len(chunks)
        chunk_hash = hashlib.sha1(
            f"{article.get('id')}|{chunk_index}|{current_heading}|{chunk_content}".encode("utf-8")
        ).hexdigest()
        metadata = {
            "article_title": article_title,
            "publish_date": article.get("publish_date"),
            "main_topic": article.get("main_topic"),
            "heading": current_heading,
        }
        chunks.append(
            {
                "chunk_index": chunk_index,
                "chunk_hash": chunk_hash,
                "heading": current_heading,
                "content": chunk_content,
                "search_text": _build_search_text(article, current_heading, chunk_content),
                "token_count": count_visible_tokens(chunk_content),
                "char_count": len(chunk_content),
                "metadata": metadata,
            }
        )
        buffer = [next_seed] if next_seed else []

    for paragraph in paragraphs:
        if _looks_like_heading(paragraph):
            if buffer:
                flush_buffer()
            heading = _clean_heading(paragraph)
            if heading:
                current_heading = heading
            continue
        for segment in _split_long_paragraph(paragraph, char_limit=char_limit, overlap=overlap):
            candidate = "\n\n".join(buffer + [segment]).strip() if buffer else segment
            if buffer and len(candidate) > char_limit:
                seed = _overlap_prefix("\n\n".join(buffer), overlap)
                flush_buffer(next_seed=seed if seed else None)
                candidate = "\n\n".join(buffer + [segment]).strip() if buffer else segment
            if len(candidate) > char_limit and not buffer:
                seed = _overlap_prefix(segment, overlap)
                buffer = [segment[:char_limit].strip()]
                flush_buffer(next_seed=seed if seed else None)
                remaining = segment[char_limit:].strip()
                if remaining:
                    buffer.append(remaining)
                continue
            buffer.append(segment)

    flush_buffer()
    return chunks
