from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException

from backend.config import (
    ELASTICSEARCH_API_KEY,
    ELASTICSEARCH_INDEX_PREFIX,
    ELASTICSEARCH_URL,
    RAG_RETRIEVAL_CANDIDATE_LIMIT,
    RAG_SEARCH_PROVIDER,
)
from backend.database import connection_scope, ensure_runtime_tables
from backend.services import ai_service
from backend.services.catalog_service import _serialize_articles
from backend.services.content_localization import contains_cjk
from backend.services.knowledge_embedding_service import cosine_similarity, embed_query_text, is_chunk_embedding_enabled
from backend.services.knowledge_ingestion_service import sync_articles_for_rag

TOKEN_SPLIT_PATTERN = re.compile(r"[\s,，。；;、/|]+")
TEXT_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)

ensure_runtime_tables()


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _copy(language: str, zh: str, en: str) -> str:
    return zh if language == "zh" else en


def _normalize_language(requested_language: str | None, text: str = "") -> str:
    normalized = "en" if str(requested_language or "").strip().lower() == "en" else "zh"
    return "zh" if contains_cjk(text) else normalized


def _normalize_text(text: str | None) -> str:
    return (text or "").strip().lower()


def _term_occurrences(text: str | None, term: str) -> int:
    normalized_text = _normalize_text(text)
    normalized_term = _normalize_text(term)
    if not normalized_text or not normalized_term:
        return 0
    return normalized_text.count(normalized_term)


def _build_terms(query: str) -> list[str]:
    base = query.strip()
    if not base:
        return []
    parts = [item.strip() for item in TOKEN_SPLIT_PATTERN.split(base) if item.strip()]
    terms = [base]
    for item in parts:
        if item not in terms:
            terms.append(item)
    for expanded in ai_service.expand_query(base):
        if expanded not in terms:
            terms.append(expanded)
    return terms[:6]


def _score_chunk(row: dict[str, Any], terms: list[str]) -> float:
    if not terms:
        return 0.0
    score = 0.0
    matched = False
    for index, term in enumerate(terms):
        weight = 1.0 if index == 0 else 0.6
        title_hits = _term_occurrences(row.get("title"), term)
        heading_hits = _term_occurrences(row.get("heading"), term)
        topic_hits = _term_occurrences(row.get("main_topic"), term)
        tag_hits = _term_occurrences(row.get("tag_text"), term)
        excerpt_hits = _term_occurrences(row.get("excerpt"), term)
        content_hits = _term_occurrences(row.get("content"), term)
        term_score = (
            title_hits * 16
            + heading_hits * 12
            + topic_hits * 8
            + tag_hits * 7
            + excerpt_hits * 5
            + min(content_hits, 12) * 1.4
        )
        if term_score > 0:
            matched = True
        score += term_score * weight
    if not matched:
        return 0.0
    publish_date = str(row.get("publish_date") or "2000-01-01")
    try:
        age_days = max((date.today() - date.fromisoformat(publish_date)).days, 1)
    except ValueError:
        age_days = 3650
    recency_boost = max(0.0, 1.25 - (age_days / 3650))
    return round(score + recency_boost, 4)


def _parse_embedding_vector(raw_value: str | None) -> list[float]:
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    values: list[float] = []
    for item in payload:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            return []
    return values


def _snippet_from_chunk(text: str, query: str, *, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    needle = str(query or "").strip()
    if not needle:
        return f"{value[:limit].rstrip()}..."
    lowered = value.lower()
    index = lowered.find(needle.lower())
    if index < 0:
        return f"{value[:limit].rstrip()}..."
    start = max(0, index - 36)
    end = min(len(value), start + limit)
    snippet = value[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(value):
        snippet = f"{snippet}..."
    return snippet


@dataclass(slots=True)
class RetrievalScope:
    scope_type: str
    user_id: str | None = None
    theme_id: int | None = None
    article_ids: list[int] | None = None


class BaseChunkProvider:
    provider_name = "base"

    def search(self, connection, *, query: str, terms: list[str], scope: RetrievalScope, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError


class LocalChunkProvider(BaseChunkProvider):
    provider_name = "local_chunk"

    def _base_query(self, scope: RetrievalScope) -> tuple[str, list[Any]]:
        filters = ["av.is_current = 1", "av.status = 'ready'"]
        params: list[Any] = []
        if scope.scope_type == "global_public":
            filters.append("COALESCE(a.access_level, 'public') = 'public'")
        if scope.article_ids:
            placeholders = ",".join("?" for _ in scope.article_ids)
            filters.append(f"a.id IN ({placeholders})")
            params.extend(int(article_id) for article_id in scope.article_ids)
        where_clause = " AND ".join(filters)
        sql = f"""
            SELECT
                ac.id AS chunk_id,
                ac.article_id,
                ac.version_id,
                ac.chunk_index,
                ac.heading,
                ac.content,
                ac.search_text,
                ac.token_count,
                ac.char_count,
                ac.metadata_json,
                a.title,
                a.slug,
                a.publish_date,
                a.source,
                a.excerpt,
                a.article_type,
                a.main_topic,
                a.view_count,
                a.cover_image_path,
                a.link,
                COALESCE(a.access_level, 'public') AS access_level,
                a.tag_text,
                ace.embedding_json,
                ace.dimensions
            FROM article_chunks ac
            JOIN article_versions av ON av.id = ac.version_id
            JOIN articles a ON a.id = ac.article_id
            LEFT JOIN article_chunk_embeddings ace ON ace.chunk_id = ac.id
            WHERE {where_clause}
            ORDER BY a.publish_date DESC, a.id DESC, ac.chunk_index ASC
        """
        return sql, params

    def search(self, connection, *, query: str, terms: list[str], scope: RetrievalScope, limit: int) -> list[dict[str, Any]]:
        sql, params = self._base_query(scope)
        rows = [dict(row) for row in connection.execute(sql, tuple(params)).fetchall()]
        query_vector = embed_query_text(query) if is_chunk_embedding_enabled() else []
        hits: list[dict[str, Any]] = []
        for row in rows:
            lexical_score = _score_chunk(row, terms)
            embedding_vector = _parse_embedding_vector(row.get("embedding_json"))
            vector_score = 0.0
            if query_vector and embedding_vector:
                vector_score = max(0.0, cosine_similarity(query_vector, embedding_vector)) * 18
            score = lexical_score + vector_score
            if score <= 0:
                continue
            row["lexical_score"] = round(lexical_score, 4)
            row["vector_score"] = round(vector_score, 4)
            row["score"] = score
            row["snippet"] = _snippet_from_chunk(row.get("content"), query)
            hits.append(row)
        hits.sort(key=lambda item: (item["score"], item["publish_date"], -int(item["chunk_index"])), reverse=True)
        return hits[: max(limit, 1)]


class ElasticChunkProvider(BaseChunkProvider):
    provider_name = "elastic"

    def search(self, connection, *, query: str, terms: list[str], scope: RetrievalScope, limit: int) -> list[dict[str, Any]]:
        del connection, query, terms, scope, limit
        if not ELASTICSEARCH_URL or not ELASTICSEARCH_API_KEY:
            raise RuntimeError("Elastic retrieval is configured but Elasticsearch credentials are missing")
        raise RuntimeError(
            f"Elastic retrieval provider is reserved for production deployment. Configure index prefix {ELASTICSEARCH_INDEX_PREFIX} in the deployment environment."
        )


def _provider() -> BaseChunkProvider:
    if RAG_SEARCH_PROVIDER == "elastic":
        return ElasticChunkProvider()
    return LocalChunkProvider()


def _theme_exists_for_user(connection, user_id: str, theme_id: int) -> None:
    row = connection.execute(
        "SELECT 1 FROM user_knowledge_themes WHERE id = ? AND user_id = ?",
        (theme_id, user_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Knowledge theme not found")


def resolve_scope_article_ids(scope: RetrievalScope) -> list[int]:
    with connection_scope() as connection:
        if scope.scope_type == "selected_articles":
            return [int(article_id) for article_id in (scope.article_ids or [])]
        if scope.scope_type == "my_theme":
            if not scope.user_id or scope.theme_id is None:
                raise HTTPException(status_code=400, detail="Theme scope requires user_id and theme_id")
            _theme_exists_for_user(connection, scope.user_id, scope.theme_id)
            rows = connection.execute(
                """
                SELECT article_id
                FROM user_knowledge_theme_articles
                WHERE theme_id = ?
                ORDER BY created_at DESC, article_id DESC
                """,
                (scope.theme_id,),
            ).fetchall()
            return [int(row["article_id"]) for row in rows]
        if scope.scope_type == "my_library":
            if not scope.user_id:
                raise HTTPException(status_code=400, detail="Library scope requires user_id")
            rows = connection.execute(
                """
                SELECT article_id
                FROM user_saved_articles
                WHERE user_id = ? AND is_active = 1
                ORDER BY updated_at DESC, article_id DESC
                """,
                (scope.user_id,),
            ).fetchall()
            return [int(row["article_id"]) for row in rows]
        if scope.scope_type == "global_public":
            return [int(article_id) for article_id in (scope.article_ids or [])]
    raise HTTPException(status_code=400, detail="Unsupported retrieval scope")


def _maybe_sync_scope_articles(scope: RetrievalScope, article_ids: list[int]) -> None:
    if not article_ids:
        return
    if scope.scope_type not in {"my_theme", "selected_articles", "my_library"}:
        return
    if len(article_ids) > 160:
        return
    sync_articles_for_rag(article_ids, trigger_source=f"{scope.scope_type}_query")


def _load_article_rows(connection, article_ids: list[int]) -> list[dict[str, Any]]:
    if not article_ids:
        return []
    placeholders = ",".join("?" for _ in article_ids)
    rows = connection.execute(
        f"""
        SELECT
            id,
            title,
            slug,
            publish_date,
            source,
            excerpt,
            article_type,
            main_topic,
            view_count,
            cover_image_path,
            link,
            access_level
        FROM articles
        WHERE id IN ({placeholders})
        """,
        tuple(article_ids),
    ).fetchall()
    by_id = {int(row["id"]): dict(row) for row in rows}
    return [by_id[article_id] for article_id in article_ids if article_id in by_id]


def _load_fallback_chunk_hits(connection, article_ids: list[int], *, limit: int) -> list[dict[str, Any]]:
    if not article_ids:
        return []
    placeholders = ",".join("?" for _ in article_ids)
    rows = connection.execute(
        f"""
        SELECT
            ac.id AS chunk_id,
            ac.article_id,
            ac.version_id,
            ac.chunk_index,
            ac.heading,
            ac.content,
            ac.search_text,
            ac.token_count,
            ac.char_count,
            ac.metadata_json,
            a.title,
            a.slug,
            a.publish_date,
            a.source,
            a.excerpt,
            a.article_type,
            a.main_topic,
            a.view_count,
            a.cover_image_path,
            a.link,
            COALESCE(a.access_level, 'public') AS access_level,
            a.tag_text
        FROM article_chunks ac
        JOIN article_versions av ON av.id = ac.version_id AND av.is_current = 1 AND av.status = 'ready'
        JOIN articles a ON a.id = ac.article_id
        WHERE a.id IN ({placeholders})
        ORDER BY a.publish_date DESC, a.id DESC, ac.chunk_index ASC
        LIMIT ?
        """,
        (*article_ids, max(limit, 1)),
    ).fetchall()
    hits: list[dict[str, Any]] = []
    fallback_score = float(len(article_ids))
    for row in rows:
        item = dict(row)
        item["score"] = fallback_score
        item["snippet"] = _snippet_from_chunk(item.get("content"), "")
        hits.append(item)
    return hits


def _aggregate_source_scores(chunk_hits: list[dict[str, Any]]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for item in chunk_hits:
        article_id = int(item["article_id"])
        scores[article_id] = max(scores.get(article_id, 0.0), float(item["score"]))
    return scores


def _serialize_sources(connection, article_ids: list[int], *, user_id: str | None, membership_profile: dict | None, language: str, scores: dict[int, float]) -> list[dict[str, Any]]:
    rows = _load_article_rows(connection, article_ids)
    items = _serialize_articles(connection, rows, current_user_id=user_id, membership_profile=membership_profile, language=language)
    for item in items:
        item["score"] = round(scores.get(int(item["id"]), 0.0), 4)
    return items


def _build_context_blocks(chunk_hits: list[dict[str, Any]], *, limit: int = 6) -> str:
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


def _log_retrieval_event(
    *,
    user_id: str | None,
    scope: RetrievalScope,
    query: str,
    provider_name: str,
    selected_article_count: int,
    returned_chunk_count: int,
    returned_article_count: int,
    latency_ms: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO retrieval_events (
                user_id,
                scope_type,
                scope_ref,
                query,
                provider,
                selected_article_count,
                returned_chunk_count,
                returned_article_count,
                latency_ms,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                scope.scope_type,
                str(scope.theme_id) if scope.theme_id is not None else None,
                query,
                provider_name,
                selected_article_count,
                returned_chunk_count,
                returned_article_count,
                latency_ms,
                json.dumps(metadata or {}, ensure_ascii=False),
                _now_iso(),
            ),
        )
        connection.commit()


def log_answer_event(
    *,
    user_id: str | None,
    scope: RetrievalScope,
    question: str,
    answer_model: str,
    selected_article_count: int,
    source_article_count: int,
    source_chunk_count: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO answer_events (
                user_id,
                scope_type,
                scope_ref,
                question,
                answer_model,
                selected_article_count,
                source_article_count,
                source_chunk_count,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                scope.scope_type,
                str(scope.theme_id) if scope.theme_id is not None else None,
                question,
                answer_model,
                selected_article_count,
                source_article_count,
                source_chunk_count,
                json.dumps(metadata or {}, ensure_ascii=False),
                _now_iso(),
            ),
        )
        connection.commit()


def retrieve_scope_context(
    query: str,
    *,
    scope: RetrievalScope,
    page_size: int = 5,
    source_limit: int | None = None,
    language: str = "zh",
    membership_profile: dict | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    response_language = _normalize_language(language, query)
    provider = _provider()
    resolved_ids = resolve_scope_article_ids(scope)
    if scope.scope_type == "selected_articles":
        resolved_ids = [int(article_id) for article_id in (scope.article_ids or [])]
    elif scope.article_ids:
        allowed_lookup = {int(article_id) for article_id in resolved_ids}
        filtered = []
        for article_id in scope.article_ids:
            current = int(article_id)
            if current in allowed_lookup and current not in filtered:
                filtered.append(current)
        resolved_ids = filtered

    _maybe_sync_scope_articles(scope, resolved_ids)
    scoped = RetrievalScope(
        scope_type=scope.scope_type,
        user_id=scope.user_id,
        theme_id=scope.theme_id,
        article_ids=resolved_ids if resolved_ids else scope.article_ids,
    )
    terms = _build_terms(query)

    with connection_scope() as connection:
        chunk_hits = provider.search(
            connection,
            query=query,
            terms=terms,
            scope=scoped,
            limit=max(page_size * 3, min(RAG_RETRIEVAL_CANDIDATE_LIMIT, 18)),
        )
        if not chunk_hits and resolved_ids:
            chunk_hits = _load_fallback_chunk_hits(connection, resolved_ids, limit=max(page_size * 2, 4))
        source_scores = _aggregate_source_scores(chunk_hits)
        effective_source_limit = max(int(source_limit or page_size), 1)
        source_ids = list(source_scores.keys())[:effective_source_limit]
        sources = _serialize_sources(
            connection,
            source_ids,
            user_id=scope.user_id,
            membership_profile=membership_profile,
            language=response_language,
            scores=source_scores,
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    _log_retrieval_event(
        user_id=scope.user_id,
        scope=scope,
        query=query,
        provider_name=provider.provider_name,
        selected_article_count=len(resolved_ids),
        returned_chunk_count=len(chunk_hits[: max(page_size * 2, 1)]),
        returned_article_count=len(sources),
        latency_ms=latency_ms,
        metadata={"language": response_language},
    )
    return {
        "language": response_language,
        "selected_article_ids": resolved_ids,
        "chunk_hits": chunk_hits[: max(page_size * 2, 1)],
        "sources": sources,
        "total_sources": len(source_scores),
        "total_chunks": len(chunk_hits),
        "context_blocks": _build_context_blocks(chunk_hits),
        "provider": provider.provider_name,
    }


def build_empty_scope_answer(scope_label: str, language: str) -> str:
    return _copy(
        language,
        f"{scope_label}里还没有可检索的文章，先把文章加入资料库或主题，再继续提问。",
        f'There is no searchable article inside {scope_label} yet. Add articles first, then continue.',
    )
