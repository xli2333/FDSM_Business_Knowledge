from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path


DEFAULT_DATABASE_NAME = "fudan_knowledge_base.db"


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _run_command(command: list[str], *, dry_run: bool = False) -> None:
    printable = " ".join(command)
    if dry_run:
        print(f"[backup] dry-run command: {printable}", flush=True)
        return
    subprocess.run(command, check=True)


def backup_once(data_dir: Path, backup_dir: Path, database_name: str = DEFAULT_DATABASE_NAME) -> Path:
    source_path = data_dir / database_name
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = backup_dir / f"{source_path.stem}.{timestamp}{source_path.suffix}"
    temp_path = backup_dir / f".{target_path.name}.tmp"
    source_uri = f"{source_path.resolve().as_uri()}?mode=ro"

    for stale_path in (temp_path, Path(f"{temp_path}-journal")):
        if stale_path.exists():
            stale_path.unlink()

    source = None
    target = None
    try:
        source = sqlite3.connect(source_uri, uri=True, timeout=30)
        target = sqlite3.connect(temp_path)
        source.backup(target)
        target.close()
        source.close()
        target = None
        source = None
        temp_path.replace(target_path)
    except Exception:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
        for stale_path in (temp_path, Path(f"{temp_path}-journal")):
            if stale_path.exists():
                try:
                    stale_path.unlink()
                except PermissionError:
                    pass
        raise

    return target_path


def compress_backup(path: Path) -> Path:
    compressed_path = path.with_suffix(path.suffix + ".gz")
    temp_path = compressed_path.with_suffix(compressed_path.suffix + ".tmp")
    try:
        with path.open("rb") as source, gzip.open(temp_path, "wb", compresslevel=6) as target:
            shutil.copyfileobj(source, target)
        temp_path.replace(compressed_path)
        path.unlink()
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return compressed_path


def encrypt_backup(path: Path, recipient: str, *, dry_run: bool = False) -> Path:
    if not recipient:
        raise ValueError("BACKUP_ENCRYPTION_RECIPIENT is required when encryption is enabled.")
    if not _command_exists("gpg") and not dry_run:
        raise RuntimeError("gpg command not found; install gnupg in the backup container/host.")
    encrypted_path = Path(f"{path}.gpg")
    command = [
        "gpg",
        "--batch",
        "--yes",
        "--trust-model",
        "always",
        "--output",
        str(encrypted_path),
        "--encrypt",
        "--recipient",
        recipient,
        str(path),
    ]
    _run_command(command, dry_run=dry_run)
    if dry_run:
        return encrypted_path
    path.unlink()
    return encrypted_path


def _copy_to_local_target(path: Path, target: str, *, dry_run: bool = False) -> None:
    target_dir = Path(target.removeprefix("file://")).expanduser()
    destination = target_dir / path.name
    if dry_run:
        print(f"[backup] dry-run local copy: {path} -> {destination}", flush=True)
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def ship_backup_offsite(path: Path, target: str, *, command_name: str = "rclone", dry_run: bool = False) -> None:
    cleaned_target = target.strip()
    if not cleaned_target:
        raise ValueError("BACKUP_OFFSITE_TARGET is required when offsite backup is enabled.")
    if cleaned_target.startswith("file://") or cleaned_target.startswith("/") or ":\\" in cleaned_target:
        _copy_to_local_target(path, cleaned_target, dry_run=dry_run)
        return
    if cleaned_target.startswith("oss://"):
        if not _command_exists("ossutil") and not dry_run:
            raise RuntimeError("ossutil command not found; install ossutil or use rclone/local target.")
        _run_command(["ossutil", "cp", str(path), cleaned_target.rstrip("/") + "/"], dry_run=dry_run)
        return
    resolved_command = command_name.strip() or "rclone"
    if not _command_exists(resolved_command) and not dry_run:
        raise RuntimeError(f"{resolved_command} command not found; install it or use file:// offsite target.")
    _run_command([resolved_command, "copy", str(path), cleaned_target], dry_run=dry_run)


def finalize_backup(path: Path, args: argparse.Namespace) -> Path:
    final_path = path
    if args.compress:
        final_path = compress_backup(final_path)
    if args.encrypt:
        final_path = encrypt_backup(final_path, args.encryption_recipient, dry_run=args.dry_run)
    if args.offsite:
        ship_backup_offsite(
            final_path,
            args.offsite_target,
            command_name=args.offsite_command,
            dry_run=args.dry_run,
        )
    return final_path


def prune_old_backups(backup_dir: Path, retention_days: int, database_name: str = DEFAULT_DATABASE_NAME) -> int:
    if retention_days <= 0 or not backup_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    stem = Path(database_name).stem
    suffix = Path(database_name).suffix
    removed = 0

    for path in backup_dir.glob(f"{stem}.*{suffix}*"):
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        except FileNotFoundError:
            continue
        if modified_at < cutoff:
            path.unlink()
            removed += 1

    return removed


def create_backup(args: argparse.Namespace) -> Path:
    raw_path = backup_once(args.data_dir, args.backup_dir, args.database_name)
    final_path = finalize_backup(raw_path, args)
    removed = prune_old_backups(args.backup_dir, args.retention_days, args.database_name)
    print(f"backup created: {final_path}; old backups removed: {removed}", flush=True)
    return final_path


def run_loop(args: argparse.Namespace) -> None:
    while True:
        create_backup(args)
        time.sleep(args.interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create SQLite backups and optionally compress, encrypt, and ship them offsite.")
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "/data")))
    parser.add_argument("--backup-dir", type=Path, default=Path(os.getenv("BACKUP_DIR", "/backups")))
    parser.add_argument("--database-name", default=os.getenv("DATABASE_NAME", DEFAULT_DATABASE_NAME))
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=int(os.getenv("BACKUP_INTERVAL_SECONDS", "86400")),
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.getenv("BACKUP_RETENTION_DAYS", "14")),
    )
    parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=_env_flag("BACKUP_COMPRESS", "1"))
    parser.add_argument("--encrypt", action=argparse.BooleanOptionalAction, default=_env_flag("BACKUP_ENCRYPTION_REQUIRED", "0"))
    parser.add_argument("--encryption-recipient", default=os.getenv("BACKUP_ENCRYPTION_RECIPIENT", "").strip())
    parser.add_argument("--offsite", action=argparse.BooleanOptionalAction, default=_env_flag("BACKUP_OFFSITE_REQUIRED", "0"))
    parser.add_argument("--offsite-target", default=os.getenv("BACKUP_OFFSITE_TARGET", "").strip())
    parser.add_argument("--offsite-command", default=os.getenv("BACKUP_OFFSITE_COMMAND", "rclone").strip() or "rclone")
    parser.add_argument("--dry-run", action="store_true", default=_env_flag("BACKUP_DRY_RUN", "0"))
    parser.add_argument("--loop", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.loop:
        run_loop(args)
        return

    create_backup(args)


if __name__ == "__main__":
    main()
