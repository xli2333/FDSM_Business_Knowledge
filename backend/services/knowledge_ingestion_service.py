from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from backend.config import RAG_ENABLE_INLINE_INGESTION
from backend.database import connection_scope, ensure_runtime_tables
from backend.services.knowledge_embedding_service import embed_chunk_texts, is_chunk_embedding_enabled
from backend.services.knowledge_chunking_service import build_article_chunks, build_article_source_hash

ensure_runtime_tables()


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _fetch_article_row(connection, article_id: int):
    row = connection.execute(
        """
        SELECT
            id,
            slug,
            title,
            publish_date,
            source,
            excerpt,
            main_topic,
            article_type,
            access_level,
            tag_text,
            link,
            content,
            updated_at
        FROM articles
        WHERE id = ?
        """,
        (article_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return row


def _serialize_version(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "article_id": int(row["article_id"]),
        "source_hash": str(row["source_hash"]),
        "status": str(row["status"]),
        "chunk_count": int(row["chunk_count"] or 0),
        "is_current": bool(row["is_current"]),
        "updated_at": row["updated_at"],
        "ingested_at": row["ingested_at"],
    }


def _serialize_job(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "article_id": int(row["article_id"]),
        "version_id": int(row["version_id"]) if row["version_id"] is not None else None,
        "trigger_source": str(row["trigger_source"]),
        "status": str(row["status"]),
        "stage": str(row["stage"]),
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def _serialize_error_result(article_id: int, error: Exception) -> dict[str, Any]:
    return {
        "job": None,
        "version": None,
        "article_id": int(article_id),
        "error": str(error),
    }


def _load_json_payload(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _current_version_row(connection, article_id: int):
    return connection.execute(
        """
        SELECT *
        FROM article_versions
        WHERE article_id = ? AND is_current = 1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()


def _latest_job_row(connection, article_id: int):
    return connection.execute(
        """
        SELECT *
        FROM ingestion_jobs
        WHERE article_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()


def _ensure_version(connection, article_row, source_hash: str, timestamp: str):
    current = _current_version_row(connection, int(article_row["id"]))
    if current is not None and str(current["source_hash"]) == source_hash:
        connection.execute(
            """
            UPDATE article_versions
            SET title = ?,
                excerpt = ?,
                main_topic = ?,
                access_level = ?,
                word_count = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                article_row["title"],
                article_row["excerpt"],
                article_row["main_topic"],
                article_row["access_level"] or "public",
                max(1, len(str(article_row["content"] or "").replace("\n", ""))),
                timestamp,
                int(current["id"]),
            ),
        )
        return current, False

    connection.execute(
        "UPDATE article_versions SET is_current = 0, updated_at = ? WHERE article_id = ?",
        (timestamp, int(article_row["id"])),
    )
    connection.execute(
        """
        INSERT INTO article_versions (
            article_id,
            source_hash,
            title,
            excerpt,
            main_topic,
            access_level,
            status,
            is_current,
            word_count,
            chunk_count,
            metadata_json,
            created_at,
            updated_at,
            ingested_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', 1, ?, 0, '{}', ?, ?, NULL)
        """,
        (
            int(article_row["id"]),
            source_hash,
            article_row["title"],
            article_row["excerpt"],
            article_row["main_topic"],
            article_row["access_level"] or "public",
            max(1, len(str(article_row["content"] or "").replace("\n", ""))),
            timestamp,
            timestamp,
        ),
    )
    version_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    version = connection.execute("SELECT * FROM article_versions WHERE id = ?", (version_id,)).fetchone()
    return version, True


def _create_job(connection, article_id: int, version_id: int, trigger_source: str, timestamp: str) -> int:
    connection.execute(
        """
        INSERT INTO ingestion_jobs (
            article_id,
            version_id,
            trigger_source,
            status,
            stage,
            metrics_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, 'pending', 'queued', '{}', ?, ?)
        """,
        (article_id, version_id, trigger_source, timestamp, timestamp),
    )
    return int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])


def _queue_job_for_article(connection, article_id: int, *, trigger_source: str, timestamp: str) -> tuple[int, Any]:
    article = _fetch_article_row(connection, article_id)
    source_hash = build_article_source_hash(article)
    version, _ = _ensure_version(connection, article, source_hash, timestamp)
    job_id = _create_job(connection, article_id, int(version["id"]), trigger_source, timestamp)
    return job_id, version


def _mark_job(connection, job_id: int, *, status: str, stage: str, timestamp: str, error_message: str | None = None, metrics: dict[str, Any] | None = None, started: bool = False, completed: bool = False) -> None:
    connection.execute(
        """
        UPDATE ingestion_jobs
        SET status = ?,
            stage = ?,
            error_message = ?,
            metrics_json = ?,
            updated_at = ?,
            started_at = CASE WHEN ? = 1 THEN COALESCE(started_at, ?) ELSE started_at END,
            completed_at = CASE WHEN ? = 1 THEN ? ELSE completed_at END
        WHERE id = ?
        """,
        (
            status,
            stage,
            error_message,
            json.dumps(metrics or {}, ensure_ascii=False),
            timestamp,
            1 if started else 0,
            timestamp,
            1 if completed else 0,
            timestamp,
            job_id,
        ),
    )


def _write_chunks(connection, *, article_row, version_id: int, chunks: list[dict[str, Any]], timestamp: str) -> list[int]:
    connection.execute("DELETE FROM article_chunk_embeddings WHERE version_id = ?", (version_id,))
    connection.execute("DELETE FROM article_chunks WHERE version_id = ?", (version_id,))
    if chunks:
        connection.executemany(
            """
            INSERT INTO article_chunks (
                article_id,
                version_id,
                chunk_index,
                chunk_hash,
                heading,
                content,
                search_text,
                token_count,
                char_count,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(article_row["id"]),
                    version_id,
                    int(chunk["chunk_index"]),
                    chunk["chunk_hash"],
                    chunk["heading"],
                    chunk["content"],
                    chunk["search_text"],
                    int(chunk["token_count"]),
                    int(chunk["char_count"]),
                    json.dumps(chunk["metadata"], ensure_ascii=False),
                    timestamp,
                    timestamp,
                )
                for chunk in chunks
            ],
        )
    rows = connection.execute(
        """
        SELECT id
        FROM article_chunks
        WHERE version_id = ?
        ORDER BY chunk_index ASC
        """,
        (version_id,),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def _build_chunk_embeddings(chunks: list[dict[str, Any]]) -> tuple[list[list[float]], dict[str, Any]]:
    if not chunks or not is_chunk_embedding_enabled():
        return [], {"embedding_count": 0, "embedding_dimensions": 0, "embedding_provider": None}
    embeddings = embed_chunk_texts([chunk["search_text"] for chunk in chunks])
    if len(embeddings) != len(chunks):
        raise RuntimeError("Chunk embedding generation mismatch")
    dimensions = len(embeddings[0]) if embeddings else 0
    return embeddings, {
        "embedding_count": len(embeddings),
        "embedding_dimensions": dimensions,
        "embedding_provider": "gemini",
    }


def _write_chunk_embeddings(
    connection,
    *,
    article_row,
    version_id: int,
    chunk_ids: list[int],
    embeddings: list[list[float]],
    timestamp: str,
) -> dict[str, Any]:
    connection.execute("DELETE FROM article_chunk_embeddings WHERE version_id = ?", (version_id,))
    if not chunk_ids or not embeddings:
        return {"embedding_count": 0, "embedding_dimensions": 0, "embedding_provider": None}
    if len(chunk_ids) != len(embeddings):
        raise RuntimeError("Chunk embedding write mismatch")
    dimensions = len(embeddings[0]) if embeddings else 0
    connection.executemany(
        """
        INSERT INTO article_chunk_embeddings (
            chunk_id,
            article_id,
            version_id,
            provider,
            dimensions,
            embedding_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                chunk_id,
                int(article_row["id"]),
                version_id,
                "gemini",
                dimensions,
                json.dumps(embedding, ensure_ascii=False),
                timestamp,
                timestamp,
            )
            for chunk_id, embedding in zip(chunk_ids, embeddings, strict=False)
        ],
    )
    return {"embedding_count": len(embeddings), "embedding_dimensions": dimensions, "embedding_provider": "gemini"}


def _finish_version(connection, version_id: int, *, status: str, chunk_count: int, timestamp: str, metadata: dict[str, Any] | None = None) -> None:
    connection.execute(
        """
        UPDATE article_versions
        SET status = ?,
            chunk_count = ?,
            metadata_json = ?,
            updated_at = ?,
            ingested_at = CASE WHEN ? = 'ready' THEN ? ELSE ingested_at END
        WHERE id = ?
        """,
        (
            status,
            chunk_count,
            json.dumps(metadata or {}, ensure_ascii=False),
            timestamp,
            status,
            timestamp,
            version_id,
        ),
    )


def process_ingestion_job(job_id: int) -> dict[str, Any]:
    article = None
    version_id: int | None = None
    source_hash = ""
    chunks: list[dict[str, Any]] = []
    chunk_ids: list[int] = []
    embedding_stats = {"embedding_count": 0, "embedding_dimensions": 0, "embedding_provider": None}

    try:
        with connection_scope() as connection:
            job = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                raise HTTPException(status_code=404, detail="Ingestion job not found")

            timestamp = _now_iso()
            _mark_job(connection, job_id, status="running", stage="loading_article", timestamp=timestamp, started=True)
            article = _fetch_article_row(connection, int(job["article_id"]))
            source_hash = build_article_source_hash(article)
            version = connection.execute("SELECT * FROM article_versions WHERE id = ?", (int(job["version_id"]),)).fetchone()
            if version is None or str(version["source_hash"]) != source_hash:
                version, _ = _ensure_version(connection, article, source_hash, timestamp)
                connection.execute(
                    "UPDATE ingestion_jobs SET version_id = ?, updated_at = ? WHERE id = ?",
                    (int(version["id"]), timestamp, job_id),
                )
            version_id = int(version["id"])
            connection.commit()

        if article is None or version_id is None:
            raise RuntimeError("Ingestion job is missing article context")

        chunks = build_article_chunks(article)

        with connection_scope() as connection:
            timestamp = _now_iso()
            _mark_job(connection, job_id, status="running", stage="chunking", timestamp=timestamp)
            chunk_ids = _write_chunks(connection, article_row=article, version_id=version_id, chunks=chunks, timestamp=timestamp)
            connection.commit()

        if is_chunk_embedding_enabled():
            with connection_scope() as connection:
                timestamp = _now_iso()
                _mark_job(connection, job_id, status="running", stage="embedding", timestamp=timestamp)
                connection.commit()
            embeddings, embedding_stats = _build_chunk_embeddings(chunks)
            with connection_scope() as connection:
                timestamp = _now_iso()
                embedding_stats = _write_chunk_embeddings(
                    connection,
                    article_row=article,
                    version_id=version_id,
                    chunk_ids=chunk_ids,
                    embeddings=embeddings,
                    timestamp=timestamp,
                )
                connection.commit()

        with connection_scope() as connection:
            timestamp = _now_iso()
            _finish_version(
                connection,
                version_id,
                status="ready",
                chunk_count=len(chunks),
                timestamp=timestamp,
                metadata={
                    "publish_date": article["publish_date"],
                    "source": article["source"],
                    **embedding_stats,
                },
            )
            _mark_job(
                connection,
                job_id,
                status="completed",
                stage="completed",
                timestamp=timestamp,
                metrics={"chunk_count": len(chunks), "source_hash": source_hash, **embedding_stats},
                completed=True,
            )
            connection.commit()
            final_job = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
            final_version = connection.execute("SELECT * FROM article_versions WHERE id = ?", (version_id,)).fetchone()
        return {
            "job": _serialize_job(final_job),
            "version": _serialize_version(final_version),
        }
    except Exception as exc:
        with connection_scope() as connection:
            timestamp = _now_iso()
            job = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
            _mark_job(
                connection,
                job_id,
                status="failed",
                stage="failed",
                timestamp=timestamp,
                error_message=str(exc),
                completed=True,
            )
            current_version_id = int(job["version_id"]) if job is not None and job["version_id"] is not None else version_id
            if current_version_id is not None:
                _finish_version(connection, current_version_id, status="failed", chunk_count=0, timestamp=timestamp)
            connection.commit()
        raise


def sync_article_for_rag(article_id: int, *, trigger_source: str = "manual", force: bool = False) -> dict[str, Any]:
    ensure_runtime_tables()
    with connection_scope() as connection:
        article = _fetch_article_row(connection, article_id)
        timestamp = _now_iso()
        source_hash = build_article_source_hash(article)
        current = _current_version_row(connection, article_id)
        if (
            not force
            and current is not None
            and str(current["source_hash"]) == source_hash
            and str(current["status"]) == "ready"
            and int(current["chunk_count"] or 0) > 0
        ):
            return {
                "job": None,
                "version": _serialize_version(current),
                "skipped": True,
            }

        version, _ = _ensure_version(connection, article, source_hash, timestamp)
        job_id = _create_job(connection, article_id, int(version["id"]), trigger_source, timestamp)
        connection.commit()

    if not RAG_ENABLE_INLINE_INGESTION:
        with connection_scope() as connection:
            job = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
            version = connection.execute("SELECT * FROM article_versions WHERE id = ?", (int(version["id"]),)).fetchone()
            return {
                "job": _serialize_job(job),
                "version": _serialize_version(version),
                "queued": True,
            }
    return process_ingestion_job(job_id)


def queue_article_ingestion(article_id: int, *, trigger_source: str = "manual") -> dict[str, Any]:
    ensure_runtime_tables()
    with connection_scope() as connection:
        job_id, version = _queue_job_for_article(connection, article_id, trigger_source=trigger_source, timestamp=_now_iso())
        connection.commit()
        job = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
        return {
            "job": _serialize_job(job),
            "version": _serialize_version(version),
            "queued": True,
        }


def sync_articles_for_rag(
    article_ids: list[int] | tuple[int, ...] | set[int],
    *,
    trigger_source: str = "scope_sync",
    force: bool = False,
    workers: int = 1,
    continue_on_error: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[int] = set()
    unique_article_ids: list[int] = []
    for raw_value in article_ids:
        article_id = int(raw_value)
        if article_id in seen:
            continue
        seen.add(article_id)
        unique_article_ids.append(article_id)

    if not unique_article_ids:
        return []

    safe_workers = max(1, min(int(workers), len(unique_article_ids)))
    if safe_workers == 1:
        for article_id in unique_article_ids:
            try:
                results.append(sync_article_for_rag(article_id, trigger_source=trigger_source, force=force))
            except Exception as exc:
                if not continue_on_error:
                    raise
                results.append(_serialize_error_result(article_id, exc))
        return results

    ordered_results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=safe_workers) as executor:
        future_map = {
            executor.submit(sync_article_for_rag, article_id, trigger_source=trigger_source, force=force): article_id
            for article_id in unique_article_ids
        }
        for future in as_completed(future_map):
            article_id = future_map[future]
            try:
                ordered_results[article_id] = future.result()
            except Exception as exc:
                if not continue_on_error:
                    raise
                ordered_results[article_id] = _serialize_error_result(article_id, exc)
    return [ordered_results[article_id] for article_id in unique_article_ids if article_id in ordered_results]


def get_current_version(article_id: int) -> dict[str, Any] | None:
    with connection_scope() as connection:
        row = _current_version_row(connection, article_id)
        return _serialize_version(row) if row is not None else None


def get_article_rag_status(article_id: int) -> dict[str, Any]:
    ensure_runtime_tables()
    with connection_scope() as connection:
        version_row = _current_version_row(connection, article_id)
        latest_job_row = _latest_job_row(connection, article_id)

        chunk_count = 0
        embedding_count = 0
        embedding_dimensions = 0
        embedding_provider = None
        version_payload = _serialize_version(version_row) if version_row is not None else None

        if version_row is not None:
            version_id = int(version_row["id"])
            chunk_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM article_chunks WHERE version_id = ?",
                    (version_id,),
                ).fetchone()[0]
            )
            embedding_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    MAX(dimensions) AS dimensions,
                    MAX(provider) AS provider
                FROM article_chunk_embeddings
                WHERE version_id = ?
                """,
                (version_id,),
            ).fetchone()
            embedding_count = int(embedding_row["total"] or 0) if embedding_row is not None else 0
            embedding_dimensions = int(embedding_row["dimensions"] or 0) if embedding_row is not None else 0
            embedding_provider = str(embedding_row["provider"]).strip() if embedding_row is not None and embedding_row["provider"] else None
            version_metadata = _load_json_payload(version_row["metadata_json"])
            if not embedding_dimensions:
                embedding_dimensions = int(version_metadata.get("embedding_dimensions") or 0)
            if not embedding_provider:
                embedding_provider = str(version_metadata.get("embedding_provider") or "").strip() or None

        latest_job = _serialize_job(latest_job_row) if latest_job_row is not None else None
        current_status = str(version_row["status"]) if version_row is not None else None
        return {
            "article_id": int(article_id),
            "version_exists": version_row is not None,
            "in_knowledge_base": bool(version_row is not None and chunk_count > 0),
            "current_version": version_payload,
            "current_version_status": current_status,
            "chunk_count": chunk_count,
            "embedding_count": embedding_count,
            "has_embeddings": embedding_count > 0,
            "embedding_dimensions": embedding_dimensions,
            "embedding_provider": embedding_provider,
            "latest_job": latest_job,
            "last_error_message": latest_job.get("error_message") if latest_job else None,
        }


def list_ingestion_jobs(*, statuses: tuple[str, ...] = ("pending", "failed"), limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    normalized_statuses = tuple(str(status).strip() for status in statuses if str(status).strip())
    with connection_scope() as connection:
        if normalized_statuses:
            placeholders = ",".join("?" for _ in normalized_statuses)
            rows = connection.execute(
                f"""
                SELECT *
                FROM ingestion_jobs
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (*normalized_statuses, safe_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM ingestion_jobs
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    return [_serialize_job(row) for row in rows]


def process_pending_ingestion_jobs(
    *,
    statuses: tuple[str, ...] = ("pending", "failed"),
    limit: int = 50,
    workers: int = 1,
    continue_on_error: bool = False,
) -> list[dict[str, Any]]:
    jobs = list_ingestion_jobs(statuses=statuses, limit=limit)
    results: list[dict[str, Any]] = []
    if not jobs:
        return results

    safe_workers = max(1, min(int(workers), len(jobs)))
    if safe_workers == 1:
        for job in jobs:
            try:
                results.append(process_ingestion_job(int(job["id"])))
            except Exception as exc:
                if not continue_on_error:
                    raise
                results.append(_serialize_error_result(int(job["article_id"]), exc))
        return results

    ordered_results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=safe_workers) as executor:
        future_map = {
            executor.submit(process_ingestion_job, int(job["id"])): (int(job["id"]), int(job["article_id"]))
            for job in jobs
        }
        for future in as_completed(future_map):
            job_id, article_id = future_map[future]
            try:
                ordered_results[job_id] = future.result()
            except Exception as exc:
                if not continue_on_error:
                    raise
                ordered_results[job_id] = _serialize_error_result(article_id, exc)
    return [ordered_results[int(job["id"])] for job in jobs if int(job["id"]) in ordered_results]


def sync_public_articles_for_rag(
    *,
    limit: int | None = None,
    include_nonpublic: bool = False,
    force: bool = False,
    workers: int = 1,
    continue_on_error: bool = False,
) -> list[dict[str, Any]]:
    with connection_scope() as connection:
        filters = []
        params: list[Any] = []
        if not include_nonpublic:
            filters.append("COALESCE(access_level, 'public') = 'public'")
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_clause = ""
        if limit is not None:
            safe_limit = max(1, int(limit))
            limit_clause = "LIMIT ?"
            params.append(safe_limit)
        rows = connection.execute(
            f"""
            SELECT id
            FROM articles
            {where_clause}
            ORDER BY publish_date DESC, id DESC
            {limit_clause}
            """,
            tuple(params),
        ).fetchall()
    return sync_articles_for_rag(
        [int(row["id"]) for row in rows],
        trigger_source="public_backfill",
        force=force,
        workers=workers,
        continue_on_error=continue_on_error,
    )
