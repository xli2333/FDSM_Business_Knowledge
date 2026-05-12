from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from backend.database import ensure_runtime_tables
from backend.services.cas_auth_service import cleanup_expired_sessions


HEARTBEAT_PATH = Path(os.getenv("HOUSEKEEPING_HEARTBEAT_PATH", "/tmp/fdsm-housekeeping.ok"))


def _write_heartbeat() -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(str(time.time()), encoding="utf-8")


def run_once() -> dict:
    ensure_runtime_tables()
    removed_sessions = cleanup_expired_sessions()
    _write_heartbeat()
    return {"removed_sessions": removed_sessions}


def run_loop(interval_seconds: int) -> None:
    while True:
        result = run_once()
        print(f"[housekeeping] removed_sessions={result['removed_sessions']}", flush=True)
        time.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run periodic database housekeeping jobs.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=max(60, int(os.getenv("HOUSEKEEPING_INTERVAL_SECONDS", "3600"))),
    )
    parser.add_argument("--loop", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.loop:
        run_loop(args.interval_seconds)
        return
    result = run_once()
    print(f"[housekeeping] removed_sessions={result['removed_sessions']}")


if __name__ == "__main__":
    main()
