from __future__ import annotations

import re
from datetime import date
from functools import lru_cache

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from rank_bm25 import BM25Okapi

from backend.config import (
    DEFAULT_PAGE_SIZE,
    FAISS_DB_DIR,
    GEMINI_EMBEDDING_MODEL,
    MAX_PAGE_SIZE,
    PRIMARY_GEMINI_KEY,
)
from backend.database import connection_scope
from backend.services import ai_service
from backend.services.catalog_service import _serialize_articles
from backend.services.content_localization import contains_cjk, localize_tag_name
from backend.services.knowledge_ingestion_service import sync_articles_for_rag
from backend.services.knowledge_retrieval_service import RetrievalScope, retrieve_scope_context

TOKEN_SPLIT_PATTERN = re.compile(r"[\s,，。；;、/|]+")
TEXT_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)


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


def _tokenize_for_bm25(text: str | None) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    for chunk in TEXT_TOKEN_PATTERN.findall(text.lower()):
        if not chunk:
            continue
        tokens.append(chunk)
        if all("\u4e00" <= character <= "\u9fff" for character in chunk):
            for size in (2, 3):
                if len(chunk) >= size:
                    tokens.extend(chunk[index : index + size] for index in range(len(chunk) - size + 1))
    return tokens


def _build_bm25_document(row: dict) -> str:
    fragments: list[str] = []
    for value, weight in (
        (row.get("title"), 3),
        (row.get("main_topic"), 2),
        (row.get("tag_text"), 2),
        (row.get("people_text"), 1),
        (row.get("org_text"), 1),
        (row.get("excerpt"), 1),
        ((row.get("content") or "")[:4000], 1),
    ):
        if value:
            fragments.extend([value] * weight)
    return " ".join(fragments)


@lru_cache(maxsize=1)
def _load_search_rows() -> list[dict]:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                id, title, slug, publish_date, source, excerpt, article_type, main_topic,
                view_count, cover_image_path, link, content, tag_text, people_text, org_text,
                (
                    SELECT GROUP_CONCAT(c.slug, ' | ')
                    FROM article_columns ac
                    JOIN columns c ON c.id = ac.column_id
                    WHERE ac.article_id = articles.id
                ) AS column_text
            FROM articles
            ORDER BY publish_date DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def refresh_search_cache() -> None:
    _load_search_rows.cache_clear()
    _load_bm25_index.cache_clear()
    _load_vectorstore.cache_clear()


@lru_cache(maxsize=1)
def _load_bm25_index():
    rows = _load_search_rows()
    article_ids: list[int] = []
    tokenized_corpus: list[list[str]] = []
    for row in rows:
        article_ids.append(row["id"])
        tokens = _tokenize_for_bm25(_build_bm25_document(row))
        tokenized_corpus.append(tokens or [str(row["id"])])
    return BM25Okapi(tokenized_corpus), article_ids


@lru_cache(maxsize=1)
def _load_vectorstore():
    if not PRIMARY_GEMINI_KEY:
        return None
    index_file = FAISS_DB_DIR / "index.faiss"
    if not index_file.exists():
        return None
    embeddings = GoogleGenerativeAIEmbeddings(
        model=GEMINI_EMBEDDING_MODEL,
        google_api_key=PRIMARY_GEMINI_KEY,
        task_type="retrieval_query",
    )
    try:
        return FAISS.load_local(
            str(FAISS_DB_DIR),
            embeddings,
            allow_dangerous_deserialization=True,
            distance_strategy=DistanceStrategy.COSINE,
        )
    except Exception:
        return None


def _matches_filters(row: dict, filters: dict) -> bool:
    tags = {item.strip() for item in filters.get("tags", []) if item and item.strip()}
    columns = {item.strip() for item in filters.get("columns", []) if item and item.strip()}
    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    if start_date and row["publish_date"] < start_date:
        return False
    if end_date and row["publish_date"] > end_date:
        return False
    if tags:
        row_tags = {item.strip() for item in (row.get("tag_text") or "").split(" | ") if item.strip()}
        if row_tags.isdisjoint(tags):
            return False
    if columns:
        row_columns = {item.strip() for item in (row.get("column_text") or "").split(" | ") if item.strip()}
        if row_columns.isdisjoint(columns):
            return False
    return True


def _relevance_score(row: dict, terms: list[str]) -> float:
    if not terms:
        return 0.0
    published = row.get("publish_date") or "2000-01-01"
    age_days = max((date.today() - date.fromisoformat(published)).days, 1)
    recency_boost = max(0.0, 1.5 - (age_days / 3650))
    score = 0.0
    matched = False
    fields = {
        "title": row.get("title"),
        "main_topic": row.get("main_topic"),
        "tag_text": row.get("tag_text"),
        "people_text": row.get("people_text"),
        "org_text": row.get("org_text"),
        "excerpt": row.get("excerpt"),
        "content": row.get("content"),
    }
    for index, term in enumerate(terms):
        weight = 1.0 if index == 0 else 0.65
        title_hits = _term_occurrences(fields["title"], term)
        topic_hits = _term_occurrences(fields["main_topic"], term)
        tag_hits = _term_occurrences(fields["tag_text"], term)
        people_hits = _term_occurrences(fields["people_text"], term)
        org_hits = _term_occurrences(fields["org_text"], term)
        excerpt_hits = _term_occurrences(fields["excerpt"], term)
        content_hits = _term_occurrences(fields["content"], term)
        term_score = (
            title_hits * 12
            + topic_hits * 8
            + tag_hits * 7
            + people_hits * 6
            + org_hits * 5
            + excerpt_hits * 4
            + min(content_hits, 8) * 1.2
        )
        if term_score > 0:
            matched = True
        score += term_score * weight
    if not matched:
        return 0.0
    popularity_boost = min((row.get("view_count") or 0) / 3000, 2.2)
    return round(score + recency_boost + popularity_boost, 4)


def _vector_scores(terms: list[str]) -> dict[int, float]:
    store = _load_vectorstore()
    if store is None or not terms:
        return {}
    scores: dict[int, float] = {}
    for index, term in enumerate(terms[:3]):
        try:
            results = store.similarity_search_with_score(term, k=10)
        except Exception:
            return {}
        weight = 1.0 if index == 0 else 0.7
        for document, distance in results:
            article_id = document.metadata.get("article_id")
            if not article_id:
                continue
            similarity = max(0.0, 1 - float(distance))
            current = scores.get(article_id, 0.0)
            scores[article_id] = max(current, similarity * 14 * weight)
    return scores


def _bm25_scores(terms: list[str]) -> dict[int, float]:
    if not terms:
        return {}
    bm25, article_ids = _load_bm25_index()
    query_tokens: list[str] = []
    for term in terms[:4]:
        for token in _tokenize_for_bm25(term):
            if token not in query_tokens:
                query_tokens.append(token)
    if not query_tokens:
        return {}
    raw_scores = bm25.get_scores(query_tokens)
    positive_scores = [score for score in raw_scores if score > 0]
    if not positive_scores:
        return {}
    max_score = max(positive_scores)
    return {
        article_id: round((float(score) / max_score) * 18, 4)
        for article_id, score in zip(article_ids, raw_scores, strict=False)
        if score > 0
    }


def _rerank_rows(query: str, rows: list[dict]) -> list[dict]:
    if not rows or not ai_service.is_ai_enabled():
        return rows
    candidate_rows = rows[: min(18, len(rows))]
    candidate_payload = [
        {
            "id": row["id"],
            "title": row["title"],
            "publish_date": row["publish_date"],
            "main_topic": row.get("main_topic") or "",
            "excerpt": row.get("excerpt") or "",
            "tags": [item.strip() for item in (row.get("tag_text") or "").split(" | ") if item.strip()][:4],
            "columns": [item.strip() for item in (row.get("column_text") or "").split(" | ") if item.strip()][:3],
        }
        for row in candidate_rows
    ]
    rerank_scores = ai_service.rerank_search_results(query, candidate_payload)
    if not rerank_scores:
        return rows
    reranked_rows = sorted(
        candidate_rows,
        key=lambda item: (rerank_scores.get(item["id"], -1.0), item["score"]),
        reverse=True,
    )
    for row in reranked_rows:
        rerank_score = rerank_scores.get(row["id"])
        if rerank_score is not None:
            row["score"] = round(row["score"] + rerank_score * 4, 4)
    return reranked_rows + rows[len(candidate_rows) :]


def search_articles(
    query: str,
    *,
    mode: str = "smart",
    language: str = "zh",
    filters: dict | None = None,
    sort: str = "relevance",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    allowed_article_ids: list[int] | set[int] | tuple[int, ...] | None = None,
) -> dict:
    filters = filters or {}
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    allowed_ids = {int(value) for value in (allowed_article_ids or [])}
    terms = _build_terms(query)
    rows = _load_search_rows()
    filtered_rows: list[dict] = []
    for base_row in rows:
        if allowed_ids and int(base_row["id"]) not in allowed_ids:
            continue
        if not _matches_filters(base_row, filters):
            continue
        filtered_rows.append(dict(base_row))

    if not query.strip():
        if sort == "popularity":
            filtered_rows.sort(key=lambda item: ((item.get("view_count") or 0), item["publish_date"]), reverse=True)
        else:
            filtered_rows.sort(key=lambda item: item["publish_date"], reverse=True)
        total = len(filtered_rows)
        start = (safe_page - 1) * safe_page_size
        page_rows = filtered_rows[start : start + safe_page_size]
        with connection_scope() as connection:
            items = _serialize_articles(connection, page_rows, language=language)
        return {
            "query": query,
            "mode": mode,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "query_terms": [],
            "items": items,
        }

    bm25_scores = _bm25_scores(terms)
    matched_rows: list[dict] = []
    for row in filtered_rows:
        if mode == "exact":
            exact_score = _term_occurrences(row.get("title"), query) * 10 + _term_occurrences(
                row.get("content"), query
            )
            if exact_score <= 0:
                continue
            row["score"] = float(exact_score)
        else:
            lexical_score = _relevance_score(row, terms)
            bm25_score = bm25_scores.get(row["id"], 0.0)
            score = lexical_score + (bm25_score * 1.35)
            if score <= 0:
                continue
            row["score"] = score
        matched_rows.append(row)

    if sort == "date":
        matched_rows.sort(key=lambda item: (item["publish_date"], item["score"]), reverse=True)
    elif sort == "popularity":
        matched_rows.sort(key=lambda item: (item.get("view_count") or 0, item["score"]), reverse=True)
    else:
        matched_rows.sort(key=lambda item: (item["score"], item["publish_date"]), reverse=True)
        matched_rows = _rerank_rows(query, matched_rows)

    if mode != "exact" and matched_rows:
        candidate_limit = min(max(safe_page * safe_page_size * 3, 24), 72)
        candidate_rows = matched_rows[:candidate_limit]
        candidate_ids = [int(row["id"]) for row in candidate_rows]
        source_limit = min(len(candidate_ids), safe_page * safe_page_size + safe_page_size)
        try:
            sync_articles_for_rag(candidate_ids[: min(len(candidate_ids), 36)], trigger_source="public_search")
            retrieval = retrieve_scope_context(
                query,
                scope=RetrievalScope(scope_type="global_public", article_ids=candidate_ids),
                page_size=max(source_limit, safe_page_size),
                source_limit=source_limit,
                language=language,
            )
            if retrieval["sources"]:
                total = int(retrieval.get("total_sources") or len(retrieval["sources"]))
                start = (safe_page - 1) * safe_page_size
                items = retrieval["sources"][start : start + safe_page_size]
                return {
                    "query": query,
                    "mode": mode,
                    "total": total,
                    "page": safe_page,
                    "page_size": safe_page_size,
                    "query_terms": terms,
                    "items": items,
                }
        except Exception:
            pass

    total = len(matched_rows)
    start = (safe_page - 1) * safe_page_size
    page_rows = matched_rows[start : start + safe_page_size]
    with connection_scope() as connection:
        items = _serialize_articles(connection, page_rows, language=language)
    for item, row in zip(items, page_rows, strict=False):
        item["score"] = row["score"]
    return {
        "query": query,
        "mode": mode,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "query_terms": terms,
        "items": items,
    }


def suggest(query: str, language: str = "zh") -> dict:
    q = query.strip()
    if language == "en":
        with connection_scope() as connection:
            if not q:
                hot_tags = connection.execute(
                    """
                    SELECT slug, name
                    FROM tags
                    WHERE category IN ('topic', 'industry')
                    ORDER BY article_count DESC, name ASC
                    LIMIT 16
                    """
                ).fetchall()
                seen: set[str] = set()
                suggestions: list[str] = []
                for row in hot_tags:
                    value = localize_tag_name(row["name"], row["slug"], language="en")
                    if not value or contains_cjk(value) or value in seen:
                        continue
                    seen.add(value)
                    suggestions.append(value)
                    if len(suggestions) >= 8:
                        break
                return {"suggestions": suggestions}

            like_pattern = f"%{q}%"
            title_rows = connection.execute(
                """
                SELECT at.title AS value
                FROM article_translations at
                JOIN articles a ON a.id = at.article_id
                WHERE at.target_lang = 'en'
                  AND at.title IS NOT NULL
                  AND at.title != ''
                  AND at.title LIKE ?
                ORDER BY a.publish_date DESC
                LIMIT 8
                """,
                (like_pattern,),
            ).fetchall()
            tag_rows = connection.execute(
                """
                SELECT slug, name
                FROM tags
                ORDER BY article_count DESC, name ASC
                LIMIT 160
                """
            ).fetchall()

        seen: set[str] = set()
        values: list[str] = []
        lowered_query = q.lower()
        for row in title_rows:
            value = str(row["value"] or "").strip()
            if not value or contains_cjk(value) or value in seen:
                continue
            seen.add(value)
            values.append(value)
        for row in tag_rows:
            value = localize_tag_name(row["name"], row["slug"], language="en")
            normalized = str(value or "").strip()
            if not normalized or contains_cjk(normalized) or normalized in seen:
                continue
            if lowered_query not in normalized.lower():
                continue
            seen.add(normalized)
            values.append(normalized)
            if len(values) >= 10:
                break
        return {"suggestions": values[:10]}

    if not q:
        with connection_scope() as connection:
            hot_tags = connection.execute(
                """
                SELECT name
                FROM tags
                WHERE category IN ('topic', 'industry')
                ORDER BY article_count DESC, name ASC
                LIMIT 8
                """
            ).fetchall()
        return {"suggestions": [row["name"] for row in hot_tags]}

    like_pattern = f"%{q}%"
    with connection_scope() as connection:
        title_rows = connection.execute(
            """
            SELECT title
            FROM articles
            WHERE title LIKE ?
            ORDER BY publish_date DESC
            LIMIT 8
            """,
            (like_pattern,),
        ).fetchall()
        tag_rows = connection.execute(
            """
            SELECT name
            FROM tags
            WHERE name LIKE ?
            ORDER BY article_count DESC, name ASC
            LIMIT 6
            """,
            (like_pattern,),
        ).fetchall()
    seen = set()
    values: list[str] = []
    for row in [*title_rows, *tag_rows]:
        value = row[0]
        if value not in seen:
            seen.add(value)
            values.append(value)
    return {"suggestions": values[:10]}
