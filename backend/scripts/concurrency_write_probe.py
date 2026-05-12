from __future__ import annotations

import argparse
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from backend.database import run_write_transaction


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def one_write(index: int, hold_seconds: float) -> str:
    task_id = f"probe-{index}-{uuid.uuid4().hex}"
    timestamp = _now_iso()

    def operation(connection) -> str:
        connection.execute(
            """
            INSERT INTO async_tasks (
                id, task_type, entity_type, entity_id, status, progress,
                payload_json, attempts, max_attempts, created_at, updated_at
            )
            VALUES (?, 'qa.concurrent_write', 'qa', ?, 'queued', 0, '{}', 0, 1, ?, ?)
            """,
            (task_id, index, timestamp, timestamp),
        )
        if hold_seconds > 0:
            time.sleep(hold_seconds)
        finished_at = _now_iso()
        connection.execute(
            """
            UPDATE async_tasks
            SET status = 'completed',
                progress = 100,
                result_json = '{}',
                updated_at = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (finished_at, finished_at, task_id),
        )
        connection.execute("DELETE FROM async_tasks WHERE id = ?", (task_id,))
        return task_id

    return run_write_transaction(operation, label="qa.concurrent_write_probe")


def main() -> None:
    parser = argparse.ArgumentParser(description="Concurrent SQLite write probe using async_tasks.")
    parser.add_argument("--total", type=int, default=80)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--hold-seconds", type=float, default=0.02)
    args = parser.parse_args()

    completed = 0
    errors: list[str] = []
    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(one_write, index, max(0.0, args.hold_seconds)) for index in range(max(1, args.total))]
        for future in as_completed(futures):
            try:
                future.result()
                completed += 1
            except Exception as exc:
                errors.append(str(exc))

    payload = {
        "total": args.total,
        "workers": args.workers,
        "hold_seconds": args.hold_seconds,
        "completed": completed,
        "error_count": len(errors),
        "errors": errors[:10],
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
