from __future__ import annotations

import json
import os
import socket
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from backend.config import (
    ASYNC_TASK_DEAD_LETTER_QUEUE_KEY,
    ASYNC_TASK_POLL_TIMEOUT_SECONDS,
    ASYNC_TASK_QUEUE_KEY,
    ASYNC_TASKS_ENABLED,
    REDIS_URL,
)
from backend.database import connection_scope, run_write_transaction

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

EDITORIAL_TASK_TYPES = {
    "auto-format": "editorial.auto_format",
    "auto-summary": "editorial.auto_summary",
    "auto-translate": "editorial.auto_translate",
}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload if payload is not None else {}, ensure_ascii=False)


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _redis_client(*, for_worker: bool = False):
    if not ASYNC_TASKS_ENABLED or not REDIS_URL:
        raise HTTPException(status_code=503, detail="Async task queue is not configured.")
    import redis

    socket_timeout = max(ASYNC_TASK_POLL_TIMEOUT_SECONDS + 10, 15) if for_worker else 5
    return redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        health_check_interval=30,
        retry_on_timeout=for_worker,
        socket_connect_timeout=5,
        socket_keepalive=True,
        socket_timeout=socket_timeout,
    )


def _is_redis_error(exc: Exception) -> bool:
    try:
        import redis

        return isinstance(exc, redis.exceptions.RedisError)
    except Exception:
        return False


def _serialize_task(row) -> dict:
    return {
        "id": row["id"],
        "task_type": row["task_type"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "status": row["status"],
        "progress": row["progress"],
        "payload": _json_loads(row["payload_json"]),
        "result": _json_loads(row["result_json"]),
        "error_message": row["error_message"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "locked_by": row["locked_by"],
        "locked_at": row["locked_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def get_async_task(task_id: str) -> dict:
    with connection_scope() as connection:
        row = connection.execute("SELECT * FROM async_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Async task not found.")
    return _serialize_task(row)


def _mark_task_failed(task_id: str, error_message: str) -> None:
    timestamp = _now_iso()

    def operation(connection) -> None:
        connection.execute(
            """
            UPDATE async_tasks
            SET status = ?,
                error_message = ?,
                updated_at = ?,
                finished_at = COALESCE(finished_at, ?)
            WHERE id = ?
            """,
            (TASK_STATUS_FAILED, error_message[:4000], timestamp, timestamp, task_id),
        )

    run_write_transaction(operation, label="async_tasks.mark_failed")


def enqueue_async_task(task_id: str) -> None:
    client = _redis_client()
    client.rpush(ASYNC_TASK_QUEUE_KEY, task_id)


def create_async_task(
    task_type: str,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    payload: dict | None = None,
    max_attempts: int = 1,
) -> dict:
    task_id = uuid.uuid4().hex
    timestamp = _now_iso()

    def operation(connection) -> None:
        connection.execute(
            """
            INSERT INTO async_tasks (
                id, task_type, entity_type, entity_id, status, progress,
                payload_json, attempts, max_attempts, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                entity_type,
                entity_id,
                TASK_STATUS_QUEUED,
                0,
                _json_dumps(payload or {}),
                max(1, max_attempts),
                timestamp,
                timestamp,
            ),
        )

    run_write_transaction(operation, label="async_tasks.create")

    try:
        enqueue_async_task(task_id)
    except Exception as exc:
        _mark_task_failed(task_id, f"Failed to enqueue async task: {exc}")
        raise HTTPException(status_code=503, detail="Async task queue is unavailable.") from exc

    return get_async_task(task_id)


def create_editorial_ai_task(editorial_id: int, operation: str, payload: dict | None = None) -> dict:
    task_type = EDITORIAL_TASK_TYPES.get(operation)
    if not task_type:
        raise HTTPException(status_code=400, detail="Unsupported editorial async operation.")
    return create_async_task(
        task_type,
        entity_type="editorial_article",
        entity_id=editorial_id,
        payload=payload or {},
        max_attempts=3,
    )


def _claim_task(task_id: str, worker_id: str) -> dict | None:
    timestamp = _now_iso()

    def operation(connection) -> dict | None:
        row = connection.execute("SELECT * FROM async_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row or row["status"] != TASK_STATUS_QUEUED:
            return None
        connection.execute(
            """
            UPDATE async_tasks
            SET status = ?,
                progress = 5,
                attempts = attempts + 1,
                locked_by = ?,
                locked_at = ?,
                started_at = COALESCE(started_at, ?),
                updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                TASK_STATUS_RUNNING,
                worker_id,
                timestamp,
                timestamp,
                timestamp,
                task_id,
                TASK_STATUS_QUEUED,
            ),
        )
        claimed = connection.execute("SELECT * FROM async_tasks WHERE id = ?", (task_id,)).fetchone()
        return _serialize_task(claimed) if claimed and claimed["status"] == TASK_STATUS_RUNNING else None

    return run_write_transaction(operation, label="async_tasks.claim")


def complete_async_task(task_id: str, result: dict | None = None) -> dict:
    timestamp = _now_iso()

    def operation(connection) -> None:
        connection.execute(
            """
            UPDATE async_tasks
            SET status = ?,
                progress = 100,
                result_json = ?,
                error_message = NULL,
                updated_at = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (TASK_STATUS_COMPLETED, _json_dumps(result or {}), timestamp, timestamp, task_id),
        )

    run_write_transaction(operation, label="async_tasks.complete")
    return get_async_task(task_id)


def fail_async_task(task_id: str, error_message: str) -> dict:
    _mark_task_failed(task_id, error_message)
    return get_async_task(task_id)


def _mark_task_failed_or_requeue(task: dict, error_message: str) -> dict:
    attempts = int(task.get("attempts") or 0)
    max_attempts = max(1, int(task.get("max_attempts") or 1))
    timestamp = _now_iso()
    if attempts < max_attempts:
        def operation(connection) -> None:
            connection.execute(
                """
                UPDATE async_tasks
                SET status = ?,
                    progress = 0,
                    error_message = ?,
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (TASK_STATUS_QUEUED, error_message[:4000], timestamp, task["id"]),
            )

        run_write_transaction(operation, label="async_tasks.requeue")
        enqueue_async_task(task["id"])
        return get_async_task(task["id"])

    _mark_task_failed(task["id"], error_message)
    try:
        _redis_client().rpush(ASYNC_TASK_DEAD_LETTER_QUEUE_KEY, task["id"])
    except Exception as exc:
        if not _is_redis_error(exc):
            raise
        print(f"async task dead-letter enqueue failed: {task['id']} {exc}", flush=True)
    return get_async_task(task["id"])


def _execute_task(task: dict) -> dict:
    task_type = task["task_type"]
    payload = task.get("payload") or {}
    entity_id = int(task["entity_id"] or 0)

    if task_type == "editorial.auto_format":
        from backend.services.editorial_service import auto_format_editorial_article

        article = auto_format_editorial_article(entity_id, payload)
        return {"editorial_id": article.get("id")}

    if task_type == "editorial.auto_summary":
        from backend.services.editorial_service import generate_editorial_summary

        article = generate_editorial_summary(entity_id)
        return {"editorial_id": article.get("id")}

    if task_type == "editorial.auto_translate":
        from backend.services.editorial_service import generate_editorial_translation

        article = generate_editorial_translation(entity_id)
        return {"editorial_id": article.get("id")}

    raise RuntimeError(f"Unsupported async task type: {task_type}")


def build_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run_worker_loop(worker_id: str | None = None) -> None:
    resolved_worker_id = worker_id or build_worker_id()
    client = _redis_client(for_worker=True)
    print(f"async worker started: {resolved_worker_id}; queue={ASYNC_TASK_QUEUE_KEY}", flush=True)

    while True:
        try:
            item = client.blpop(ASYNC_TASK_QUEUE_KEY, timeout=ASYNC_TASK_POLL_TIMEOUT_SECONDS)
        except Exception as exc:
            if not _is_redis_error(exc):
                raise
            print(f"async worker redis wait failed: {exc}; reconnecting", flush=True)
            time.sleep(2)
            client = _redis_client(for_worker=True)
            continue

        if not item:
            continue

        _, task_id = item
        task = _claim_task(str(task_id), resolved_worker_id)
        if not task:
            continue

        try:
            result = _execute_task(task)
            complete_async_task(task["id"], result)
            print(f"async task completed: {task['id']} {task['task_type']}", flush=True)
        except Exception as exc:
            updated_task = _mark_task_failed_or_requeue(task, str(exc) or exc.__class__.__name__)
            print(
                f"async task {updated_task['status']}: {task['id']} "
                f"attempt={updated_task['attempts']}/{updated_task['max_attempts']} {exc}",
                flush=True,
            )
            time.sleep(1)


def queue_healthcheck() -> None:
    client = _redis_client()
    client.ping()
    with connection_scope() as connection:
        connection.execute("SELECT 1").fetchone()
