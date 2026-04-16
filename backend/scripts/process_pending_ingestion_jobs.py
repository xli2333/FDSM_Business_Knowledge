from __future__ import annotations

import argparse
import json

from backend.database import ensure_runtime_tables
from backend.services.knowledge_ingestion_service import process_pending_ingestion_jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending or failed RAG ingestion jobs.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of jobs to process.")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers for the pending-job runner.")
    parser.add_argument(
        "--statuses",
        nargs="*",
        default=("pending", "failed"),
        help="Job statuses to process. Defaults to pending failed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_tables()
    results = process_pending_ingestion_jobs(
        statuses=tuple(args.statuses or ()),
        limit=args.limit,
        workers=args.workers,
        continue_on_error=True,
    )
    payload = {
        "processed": len(results),
        "completed": sum(1 for item in results if (item.get("job") or {}).get("status") == "completed"),
        "failed": sum(1 for item in results if item.get("error")),
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
