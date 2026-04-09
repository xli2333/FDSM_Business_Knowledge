from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import get_connection
from backend.services.article_visibility_service import is_hidden_low_value_article

TOTAL_SHARDS = 12
CHUNK_SIZE = 4
WORKER_PREFIX = "round65-full-"
STALE_MINUTES = 10
RESTART_AFTER_STALE_MINUTES = 12
CHECK_INTERVAL_SECONDS = 30


def expected_shard_counts() -> dict[str, int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, content, publish_date
            FROM articles
            WHERE source != 'editorial'
            ORDER BY publish_date DESC, id DESC
            """
        ).fetchall()
    visible_rows = [row for row in rows if not is_hidden_low_value_article(row)]
    counts = {f"{WORKER_PREFIX}{index:02d}": 0 for index in range(TOTAL_SHARDS)}
    for position, _row in enumerate(visible_rows):
        shard_index = position % TOTAL_SHARDS
        counts[f"{WORKER_PREFIX}{shard_index:02d}"] += 1
    return counts


def current_worker_progress() -> dict[str, dict[str, object]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT worker_name, COUNT(DISTINCT article_id) AS article_count, MAX(updated_at) AS updated_at
            FROM article_ai_outputs
            WHERE worker_name LIKE 'round65-full-%'
            GROUP BY worker_name
            """
        ).fetchall()
    payload: dict[str, dict[str, object]] = {}
    for row in rows:
        payload[row["worker_name"]] = {
            "article_count": int(row["article_count"] or 0),
            "updated_at": str(row["updated_at"] or ""),
        }
    return payload


def running_shard_workers() -> dict[str, list[int]]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*rerender_fudan_html_batch.py*' } | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        check=False,
    )
    payload = {f"{WORKER_PREFIX}{index:02d}": [] for index in range(TOTAL_SHARDS)}
    raw = (completed.stdout or "").strip()
    if not raw:
        return payload
    try:
        records = json.loads(raw)
    except json.JSONDecodeError:
        append_log(f"warning process-scan returned invalid json: {raw[:200]}")
        return payload
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        return payload
    for record in records:
        if not isinstance(record, dict):
            continue
        pid = int(record.get("ProcessId") or 0)
        command_line = str(record.get("CommandLine") or "")
        if not pid or not command_line:
            continue
        for index in range(TOTAL_SHARDS):
            worker_name = f"{WORKER_PREFIX}{index:02d}"
            if worker_name in command_line:
                payload[worker_name].append(pid)
                break
    return payload


def kill_process_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def append_log(message: str) -> None:
    log_dir = PROJECT_ROOT / "reports"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "round65_watchdog.log"
    timestamp = datetime.now().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def restart_worker(worker_name: str) -> None:
    shard_index = int(worker_name.rsplit("-", 1)[-1])
    subprocess.Popen(
        [
            sys.executable,
            "backend/scripts/rerender_fudan_html_batch.py",
            "--chunk-size",
            str(CHUNK_SIZE),
            "--shard-index",
            str(shard_index),
            "--total-shards",
            str(TOTAL_SHARDS),
            "--worker-name",
            worker_name,
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    append_log(f"restarted {worker_name}")


def main() -> int:
    expected = expected_shard_counts()
    append_log(f"watchdog started | expected={json.dumps(expected, ensure_ascii=False)}")
    while True:
        progress = current_worker_progress()
        running = running_shard_workers()
        now = datetime.now()
        for worker_name, expected_count in expected.items():
            current = progress.get(worker_name, {})
            current_count = int(current.get("article_count") or 0)
            updated_at_raw = str(current.get("updated_at") or "").strip()
            updated_at = None
            if updated_at_raw:
                try:
                    updated_at = datetime.fromisoformat(updated_at_raw)
                except ValueError:
                    updated_at = None

            if current_count >= expected_count:
                continue

            active_pids = running.get(worker_name) or []
            if active_pids:
                if updated_at and now - updated_at > timedelta(minutes=RESTART_AFTER_STALE_MINUTES):
                    append_log(
                        f"restart stale {worker_name} | count={current_count}/{expected_count} | last_update={updated_at_raw} | pids={active_pids}"
                    )
                    for pid in active_pids:
                        kill_process_tree(pid)
                    restart_worker(worker_name)
                    continue
                if updated_at and now - updated_at > timedelta(minutes=STALE_MINUTES):
                    append_log(
                        f"warning {worker_name} appears stale | count={current_count}/{expected_count} | last_update={updated_at_raw} | pids={active_pids}"
                    )
                continue

            append_log(
                f"missing {worker_name} | count={current_count}/{expected_count} | last_update={updated_at_raw or 'none'}"
            )
            restart_worker(worker_name)

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
