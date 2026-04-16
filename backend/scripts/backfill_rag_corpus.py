from __future__ import annotations

import argparse
import json

from backend.database import ensure_runtime_tables
from backend.services.knowledge_ingestion_service import sync_public_articles_for_rag


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill RAG chunks for the public article corpus.")
    parser.add_argument("--limit", type=int, default=None, help="Only backfill the latest N articles.")
    parser.add_argument("--include-nonpublic", action="store_true", help="Include member/paid articles in the backfill run.")
    parser.add_argument("--force", action="store_true", help="Force rebuild even when the current version is already ready.")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers for the backfill run.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep processing remaining articles when a single article fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_tables()
    results = sync_public_articles_for_rag(
        limit=args.limit,
        include_nonpublic=args.include_nonpublic,
        force=args.force,
        workers=args.workers,
        continue_on_error=args.continue_on_error,
    )
    payload = {
        "processed": len(results),
        "completed": sum(1 for item in results if (item.get("job") or {}).get("status") == "completed"),
        "skipped": sum(1 for item in results if item.get("skipped")),
        "failed": sum(1 for item in results if item.get("error")),
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
