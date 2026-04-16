from __future__ import annotations

from typing import Any

from backend.database import connection_scope, ensure_runtime_tables


def _serialize_asset(row) -> dict[str, Any]:
    return {
        "article_id": int(row["article_id"]),
        "slug": str(row["slug"] or ""),
        "title": str(row["title"] or ""),
        "publish_date": str(row["publish_date"] or ""),
        "access_level": str(row["access_level"] or "public"),
        "version_id": int(row["version_id"]) if row["version_id"] is not None else None,
        "version_status": str(row["version_status"]).strip() if row["version_status"] else None,
        "chunk_count": int(row["chunk_count"] or 0),
        "embedding_count": int(row["embedding_count"] or 0),
        "embedding_provider": str(row["embedding_provider"]).strip() if row["embedding_provider"] else None,
        "version_updated_at": str(row["version_updated_at"] or ""),
        "ingested_at": str(row["ingested_at"]).strip() if row["ingested_at"] else None,
        "latest_job_status": str(row["latest_job_status"]).strip() if row["latest_job_status"] else None,
        "latest_job_stage": str(row["latest_job_stage"]).strip() if row["latest_job_stage"] else None,
        "latest_job_updated_at": str(row["latest_job_updated_at"]).strip() if row["latest_job_updated_at"] else None,
        "latest_job_completed_at": str(row["latest_job_completed_at"]).strip() if row["latest_job_completed_at"] else None,
        "latest_job_error": str(row["latest_job_error"]).strip() if row["latest_job_error"] else None,
    }


def _serialize_job(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "article_id": int(row["article_id"]),
        "version_id": int(row["version_id"]) if row["version_id"] is not None else None,
        "slug": str(row["slug"] or ""),
        "title": str(row["title"] or ""),
        "publish_date": str(row["publish_date"] or ""),
        "trigger_source": str(row["trigger_source"] or ""),
        "status": str(row["status"] or ""),
        "stage": str(row["stage"] or ""),
        "chunk_count": int(row["chunk_count"] or 0),
        "embedding_count": int(row["embedding_count"] or 0),
        "error_message": str(row["error_message"]).strip() if row["error_message"] else None,
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "started_at": str(row["started_at"]).strip() if row["started_at"] else None,
        "completed_at": str(row["completed_at"]).strip() if row["completed_at"] else None,
    }


def _serialize_retrieval(row) -> dict[str, Any]:
    return {
        "created_at": str(row["created_at"] or ""),
        "scope_type": str(row["scope_type"] or ""),
        "query": str(row["query"] or ""),
        "provider": str(row["provider"] or ""),
        "returned_chunk_count": int(row["returned_chunk_count"] or 0),
        "returned_article_count": int(row["returned_article_count"] or 0),
        "latency_ms": int(row["latency_ms"] or 0),
    }


def _serialize_answer(row) -> dict[str, Any]:
    return {
        "created_at": str(row["created_at"] or ""),
        "scope_type": str(row["scope_type"] or ""),
        "question": str(row["question"] or ""),
        "answer_model": str(row["answer_model"]).strip() if row["answer_model"] else None,
        "source_article_count": int(row["source_article_count"] or 0),
        "source_chunk_count": int(row["source_chunk_count"] or 0),
    }


def get_rag_admin_overview(*, asset_limit: int = 12, job_limit: int = 12, event_limit: int = 8) -> dict[str, Any]:
    ensure_runtime_tables()
    safe_asset_limit = max(1, min(int(asset_limit), 50))
    safe_job_limit = max(1, min(int(job_limit), 50))
    safe_event_limit = max(1, min(int(event_limit), 30))

    with connection_scope() as connection:
        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS current_version_count,
                SUM(CASE WHEN av.status = 'ready' THEN 1 ELSE 0 END) AS ready_article_count,
                SUM(CASE WHEN av.status <> 'ready' THEN 1 ELSE 0 END) AS processing_article_count,
                COALESCE(SUM(av.chunk_count), 0) AS total_chunk_count,
                MAX(COALESCE(av.ingested_at, av.updated_at)) AS latest_processed_at
            FROM article_versions av
            JOIN articles a ON a.id = av.article_id
            WHERE av.is_current = 1
              AND COALESCE(a.access_level, 'public') = 'public'
            """
        ).fetchone()
        total_embedding_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM article_chunk_embeddings ace
                JOIN article_versions av ON av.id = ace.version_id
                JOIN articles a ON a.id = av.article_id
                WHERE av.is_current = 1
                  AND COALESCE(a.access_level, 'public') = 'public'
                """
            ).fetchone()[0]
        )
        pending_job_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM ingestion_jobs j
                JOIN articles a ON a.id = j.article_id
                JOIN (
                    SELECT article_id, MAX(id) AS latest_id
                    FROM ingestion_jobs
                    GROUP BY article_id
                ) latest ON latest.latest_id = j.id
                WHERE j.status = 'pending'
                  AND COALESCE(a.access_level, 'public') = 'public'
                """
            ).fetchone()[0]
        )
        failed_job_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM ingestion_jobs j
                JOIN articles a ON a.id = j.article_id
                JOIN (
                    SELECT article_id, MAX(id) AS latest_id
                    FROM ingestion_jobs
                    GROUP BY article_id
                ) latest ON latest.latest_id = j.id
                WHERE j.status = 'failed'
                  AND COALESCE(a.access_level, 'public') = 'public'
                """
            ).fetchone()[0]
        )

        latest_assets = connection.execute(
            """
            SELECT
                av.id AS version_id,
                av.article_id,
                a.slug,
                av.title,
                COALESCE(a.publish_date, '') AS publish_date,
                COALESCE(a.access_level, 'public') AS access_level,
                av.status AS version_status,
                av.chunk_count,
                av.updated_at AS version_updated_at,
                av.ingested_at,
                COALESCE(emb.total, 0) AS embedding_count,
                emb.provider AS embedding_provider,
                latest_job.status AS latest_job_status,
                latest_job.stage AS latest_job_stage,
                latest_job.updated_at AS latest_job_updated_at,
                latest_job.completed_at AS latest_job_completed_at,
                latest_job.error_message AS latest_job_error
            FROM article_versions av
            JOIN articles a ON a.id = av.article_id
            LEFT JOIN (
                SELECT version_id, COUNT(*) AS total, MAX(provider) AS provider
                FROM article_chunk_embeddings
                GROUP BY version_id
            ) emb ON emb.version_id = av.id
            LEFT JOIN (
                SELECT j1.article_id, j1.status, j1.stage, j1.updated_at, j1.completed_at, j1.error_message
                FROM ingestion_jobs j1
                JOIN (
                    SELECT article_id, MAX(id) AS latest_id
                    FROM ingestion_jobs
                    GROUP BY article_id
                ) latest ON latest.latest_id = j1.id
            ) latest_job ON latest_job.article_id = av.article_id
            WHERE av.is_current = 1
              AND COALESCE(a.access_level, 'public') = 'public'
            ORDER BY COALESCE(av.ingested_at, av.updated_at) DESC, av.id DESC
            LIMIT ?
            """,
            (safe_asset_limit,),
        ).fetchall()

        latest_jobs = connection.execute(
            """
            SELECT
                ij.id,
                ij.article_id,
                ij.version_id,
                a.slug,
                a.title,
                COALESCE(a.publish_date, '') AS publish_date,
                ij.trigger_source,
                ij.status,
                ij.stage,
                ij.error_message,
                ij.created_at,
                ij.updated_at,
                ij.started_at,
                ij.completed_at,
                COALESCE(av.chunk_count, 0) AS chunk_count,
                COALESCE(emb.total, 0) AS embedding_count
            FROM ingestion_jobs ij
            JOIN articles a ON a.id = ij.article_id
            LEFT JOIN article_versions av ON av.id = ij.version_id
            LEFT JOIN (
                SELECT version_id, COUNT(*) AS total
                FROM article_chunk_embeddings
                GROUP BY version_id
            ) emb ON emb.version_id = ij.version_id
            WHERE COALESCE(a.access_level, 'public') = 'public'
            ORDER BY COALESCE(ij.completed_at, ij.updated_at, ij.created_at) DESC, ij.id DESC
            LIMIT ?
            """,
            (safe_job_limit,),
        ).fetchall()

        recent_retrievals = connection.execute(
            """
            SELECT created_at, scope_type, query, provider, returned_chunk_count, returned_article_count, latency_ms
            FROM retrieval_events
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (safe_event_limit,),
        ).fetchall()

        recent_answers = connection.execute(
            """
            SELECT created_at, scope_type, question, answer_model, source_article_count, source_chunk_count
            FROM answer_events
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (safe_event_limit,),
        ).fetchall()

    return {
        "current_version_count": int(summary["current_version_count"] or 0) if summary is not None else 0,
        "ready_article_count": int(summary["ready_article_count"] or 0) if summary is not None else 0,
        "processing_article_count": int(summary["processing_article_count"] or 0) if summary is not None else 0,
        "total_chunk_count": int(summary["total_chunk_count"] or 0) if summary is not None else 0,
        "total_embedding_count": total_embedding_count,
        "pending_job_count": pending_job_count,
        "failed_job_count": failed_job_count,
        "latest_processed_at": str(summary["latest_processed_at"]).strip() if summary is not None and summary["latest_processed_at"] else None,
        "latest_assets": [_serialize_asset(row) for row in latest_assets],
        "latest_jobs": [_serialize_job(row) for row in latest_jobs],
        "recent_retrievals": [_serialize_retrieval(row) for row in recent_retrievals],
        "recent_answers": [_serialize_answer(row) for row in recent_answers],
    }
