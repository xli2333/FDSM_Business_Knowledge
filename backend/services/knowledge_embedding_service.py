from __future__ import annotations

import itertools
import math
import time
from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.config import (
    GEMINI_API_KEYS,
    GEMINI_EMBEDDING_MODEL,
    PRIMARY_GEMINI_KEY,
    RAG_CHUNK_EMBEDDINGS_ENABLED,
)

_EMBEDDING_REQUEST_COUNTER = itertools.count()


@lru_cache(maxsize=1)
def get_embedding_api_keys() -> tuple[str, ...]:
    keys: list[str] = []
    for raw_key in (PRIMARY_GEMINI_KEY, *GEMINI_API_KEYS):
        cleaned = str(raw_key or "").strip()
        if cleaned and cleaned not in keys:
            keys.append(cleaned)
    return tuple(keys)


def is_chunk_embedding_enabled() -> bool:
    return bool(RAG_CHUNK_EMBEDDINGS_ENABLED and get_embedding_api_keys())


@lru_cache(maxsize=32)
def _embedding_client(api_key: str, task_type: str) -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model=GEMINI_EMBEDDING_MODEL,
        google_api_key=api_key,
        task_type=task_type,
    )


def _invoke_embedding_documents(texts: list[str]) -> list[list[float]]:
    api_keys = list(get_embedding_api_keys())
    if not api_keys:
        return []
    cleaned = [str(text or "").strip() for text in texts]
    start_offset = next(_EMBEDDING_REQUEST_COUNTER)
    max_attempts = max(3, len(api_keys) * 2)
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        api_key = api_keys[(start_offset + attempt) % len(api_keys)]
        client = _embedding_client(api_key, "retrieval_document")
        try:
            return [list(vector) for vector in client.embed_documents(cleaned)]
        except Exception as exc:
            last_error = exc
            time.sleep(min(4.0, 0.5 * (attempt + 1)))
            continue

    raise RuntimeError(f"Error embedding content: {last_error or 'unknown error'}")


def _invoke_embedding_query(text: str) -> list[float]:
    api_keys = list(get_embedding_api_keys())
    if not api_keys:
        return []
    cleaned = str(text or "").strip()
    start_offset = next(_EMBEDDING_REQUEST_COUNTER)
    max_attempts = max(3, len(api_keys) * 2)

    for attempt in range(max_attempts):
        api_key = api_keys[(start_offset + attempt) % len(api_keys)]
        client = _embedding_client(api_key, "retrieval_query")
        try:
            return list(client.embed_query(cleaned))
        except Exception:
            time.sleep(min(4.0, 0.5 * (attempt + 1)))
            continue

    return []


def embed_chunk_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if not is_chunk_embedding_enabled():
        return []
    return _invoke_embedding_documents(texts)


def embed_query_text(text: str) -> list[float]:
    if not is_chunk_embedding_enabled():
        return []
    return _invoke_embedding_query(text)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)
