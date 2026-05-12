from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _run_gpg_decrypt(source: Path, target: Path, command: str) -> None:
    args = [command, "--batch", "--yes", "--decrypt", "--output", str(target), str(source)]
    subprocess.run(args, check=True)


def _materialize_backup(source: Path, work_dir: Path, *, gpg_command: str) -> Path:
    current = source
    if current.name.endswith(".gpg"):
        decrypted = work_dir / current.name.removesuffix(".gpg")
        _run_gpg_decrypt(current, decrypted, gpg_command)
        current = decrypted

    if current.name.endswith(".gz"):
        decompressed = work_dir / current.name.removesuffix(".gz")
        with gzip.open(current, "rb") as input_file, decompressed.open("wb") as output_file:
            shutil.copyfileobj(input_file, output_file)
        current = decompressed

    return current


def _sqlite_quick_check(db_path: Path) -> str:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("PRAGMA quick_check").fetchone()
        result = str(row[0] if row else "")
    finally:
        connection.close()
    if result.lower() != "ok":
        raise RuntimeError(f"SQLite quick_check failed: {result}")
    return result


def _restore_database(source_db: Path, target_db: Path) -> Path | None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if target_db.exists():
        backup_path = target_db.with_name(f"{target_db.name}.pre-restore-{_timestamp()}")
        shutil.copy2(target_db, backup_path)

    temp_target = target_db.with_name(f".{target_db.name}.restore-{_timestamp()}.tmp")
    shutil.copy2(source_db, temp_target)
    temp_target.replace(target_db)
    return backup_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify or restore a SQLite backup created by backup_sqlite.py.")
    parser.add_argument("backup_file", type=Path)
    parser.add_argument("--target-db", type=Path, default=Path("data/fudan_knowledge_base.db"))
    parser.add_argument("--restore", action="store_true", help="Replace --target-db after verification.")
    parser.add_argument("--gpg-command", default="gpg")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.backup_file
    if not source.exists():
        raise SystemExit(f"backup file not found: {source}")

    with tempfile.TemporaryDirectory(prefix="fdsm-restore-") as temp_dir:
        materialized = _materialize_backup(source.resolve(), Path(temp_dir), gpg_command=args.gpg_command)
        quick_check = _sqlite_quick_check(materialized)
        backup_before_restore = None
        if args.restore:
            backup_before_restore = _restore_database(materialized, args.target_db)
            _sqlite_quick_check(args.target_db)

    payload = {
        "backup_file": str(source),
        "target_db": str(args.target_db),
        "quick_check": quick_check,
        "restored": bool(args.restore),
        "previous_db_backup": str(backup_before_restore) if backup_before_restore else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
