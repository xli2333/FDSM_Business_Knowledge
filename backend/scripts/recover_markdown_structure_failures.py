from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import BUSINESS_DATA_DIR
from backend.database import connection_scope, ensure_database_ready, ensure_runtime_tables
from backend.scripts.article_ai_batch import load_api_keys, make_logger
from backend.scripts.article_relayout_batch import build_manifest, fetch_existing_output_row, process_article
from backend.services.article_asset_service import build_article_source_hash, now_iso
from backend.services.markdown_structure_quality_service import markdown_structure_quality_signals

OUTPUT_PATH = BUSINESS_DATA_DIR / "article_relayout_batch" / "markdown_structure_failures.json"
STATE_DIR = BUSINESS_DATA_DIR / "article_relayout_batch" / "round67_markdown_structure_state"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect and recover markdown structure failures with Gemini relayout.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan visible articles and list markdown structure failures.")
    scan_parser.add_argument("--limit", type=int, default=0)
    scan_parser.add_argument("--ids", nargs="*", type=int, default=[])

    run_parser = subparsers.add_parser("run", help="Run Gemini relayout on detected markdown structure failures.")
    run_parser.add_argument("--limit", type=int, default=0)
    run_parser.add_argument("--ids", nargs="*", type=int, default=[])
    run_parser.add_argument("--worker-name", type=str, default="round67-markdown-structure")
    run_parser.add_argument("--force", action="store_true")
    run_parser.add_argument("--shard-index", type=int, default=0)
    run_parser.add_argument("--total-shards", type=int, default=1)
    run_parser.add_argument("--rescan", action="store_true")

    return parser.parse_args()


def _target_article_ids(*, limit: int, ids: list[int]) -> list[int]:
    explicit_ids = [article_id for article_id in ids if article_id > 0]
    if explicit_ids:
        return explicit_ids[: max(limit, 0)] if limit > 0 else explicit_ids
    manifest = build_manifest(force=False)
    visible_ids = [item["article_id"] for item in manifest]
    return visible_ids[: max(limit, 0)] if limit > 0 else visible_ids


def scan_failures(*, article_ids: list[int], persist: bool = True) -> dict[str, object]:
    failures: list[dict[str, object]] = []
    with connection_scope() as connection:
        for article_id in article_ids:
            article = connection.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            if article is None:
                continue
            article_payload = dict(article)
            source_hash = build_article_source_hash(article_payload)
            ai_row = fetch_existing_output_row(connection, article_id, source_hash)
            if ai_row is None:
                continue
            ai_payload = dict(ai_row)
            signals = markdown_structure_quality_signals(
                source_text=str(article_payload.get("content") or ""),
                formatted_markdown=str(ai_payload.get("formatted_markdown_zh") or ""),
                summary_text=str(ai_payload.get("summary_zh") or ""),
            )
            if not signals["needs_rerun"]:
                continue
            failures.append(
                {
                    "article_id": article_id,
                    "title": article_payload.get("title") or "",
                    "worker_name": ai_payload.get("worker_name") or "",
                    "format_model": ai_payload.get("format_model") or "",
                    "summary_model": ai_payload.get("summary_model") or "",
                    "updated_at": ai_payload.get("updated_at") or ai_payload.get("created_at") or "",
                    "signals": signals,
                }
            )

    payload = {
        "generated_at": now_iso(),
        "article_count": len(article_ids),
        "failure_count": len(failures),
        "failures": failures,
    }
    if persist:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _load_failure_payload(*, article_ids: list[int], rescan: bool) -> dict[str, object]:
    if not rescan and OUTPUT_PATH.exists():
        payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        if payload.get("failures"):
            return payload
    return scan_failures(article_ids=article_ids, persist=True)


def _assigned_failure_ids(
    *,
    payload: dict[str, object],
    explicit_ids: list[int],
    shard_index: int,
    total_shards: int,
) -> list[int]:
    if explicit_ids:
        return [article_id for article_id in explicit_ids if article_id > 0]
    failures = [int(item["article_id"]) for item in payload.get("failures", [])]
    if total_shards <= 1:
        return failures
    return [article_id for index, article_id in enumerate(failures) if index % total_shards == shard_index]


def _state_path(worker_name: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{worker_name}.json"


def _write_state(worker_name: str, payload: dict[str, object]) -> None:
    _state_path(worker_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_recovery(
    *,
    article_ids: list[int],
    explicit_ids: list[int],
    worker_name: str,
    force: bool,
    shard_index: int,
    total_shards: int,
    rescan: bool,
) -> dict[str, object]:
    logger = make_logger(f"relayout.{worker_name}")
    api_keys = load_api_keys()
    payload = scan_failures(article_ids=article_ids, persist=False) if explicit_ids else _load_failure_payload(article_ids=article_ids, rescan=rescan)
    target_ids = _assigned_failure_ids(
        payload=payload,
        explicit_ids=explicit_ids,
        shard_index=shard_index,
        total_shards=total_shards,
    )

    state = {
        "generated_at": now_iso(),
        "worker_name": worker_name,
        "status": "running",
        "shard_index": shard_index,
        "total_shards": total_shards,
        "target_count": len(target_ids),
        "processed": 0,
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "current_article_id": None,
    }
    _write_state(worker_name, state)

    results: list[dict[str, object]] = []
    for index, article_id in enumerate(target_ids, start=1):
        state["current_article_id"] = article_id
        _write_state(worker_name, state)
        try:
            status = process_article(
                article_id,
                worker_name=worker_name,
                api_keys=api_keys,
                sequence_index=index,
                logger=logger,
                force=force,
            )
            results.append({"article_id": article_id, "status": status})
            state["processed"] += 1
            if status == "completed":
                state["completed"] += 1
            elif status == "skipped":
                state["skipped"] += 1
            else:
                state["failed"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Markdown structure recovery failed on article %s: %s", article_id, exc)
            results.append({"article_id": article_id, "status": "failed", "error": str(exc)})
            state["processed"] += 1
            state["failed"] += 1
        _write_state(worker_name, state)

    final_payload = {
        "generated_at": now_iso(),
        "worker_name": worker_name,
        "shard_index": shard_index,
        "total_shards": total_shards,
        "target_count": len(target_ids),
        "results": results,
    }
    state["status"] = "completed"
    state["current_article_id"] = None
    _write_state(worker_name, state)
    return final_payload


def main() -> int:
    args = parse_args()
    ensure_database_ready()
    ensure_runtime_tables()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    article_ids = _target_article_ids(limit=max(args.limit, 0), ids=list(args.ids or []))
    if args.command == "scan":
        payload = scan_failures(article_ids=article_ids, persist=True)
    else:
        payload = run_recovery(
            article_ids=article_ids,
            explicit_ids=list(args.ids or []),
            worker_name=args.worker_name,
            force=bool(args.force),
            shard_index=max(int(args.shard_index), 0),
            total_shards=max(int(args.total_shards), 1),
            rescan=bool(args.rescan),
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
