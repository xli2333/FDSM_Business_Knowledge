from __future__ import annotations

import json
from pathlib import Path

from backend.config import BUSINESS_DATA_DIR

FAILURE_PATH = BUSINESS_DATA_DIR / "article_relayout_batch" / "markdown_structure_failures.json"
STATE_DIR = BUSINESS_DATA_DIR / "article_relayout_batch" / "round67_markdown_structure_state"


def main() -> int:
    total_targets = 0
    if FAILURE_PATH.exists():
        payload = json.loads(FAILURE_PATH.read_text(encoding="utf-8"))
        total_targets = int(payload.get("failure_count") or 0)

    states = []
    if STATE_DIR.exists():
        for path in sorted(STATE_DIR.glob("round67-*.json")):
            try:
                states.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue

    processed = sum(int(item.get("processed") or 0) for item in states)
    completed = sum(int(item.get("completed") or 0) for item in states)
    skipped = sum(int(item.get("skipped") or 0) for item in states)
    failed = sum(int(item.get("failed") or 0) for item in states)
    running = [item for item in states if item.get("status") == "running"]

    payload = {
        "total_targets": total_targets,
        "worker_count": len(states),
        "running_workers": len(running),
        "processed": processed,
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
        "remaining_estimate": max(total_targets - processed, 0),
        "workers": [
            {
                "worker_name": item.get("worker_name"),
                "status": item.get("status"),
                "processed": item.get("processed"),
                "target_count": item.get("target_count"),
                "current_article_id": item.get("current_article_id"),
            }
            for item in states
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
