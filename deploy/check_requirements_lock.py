from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
LOCK = ROOT / "requirements.lock.txt"


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def parse_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.split(r"[<>=!~; ]", line, maxsplit=1)[0]
        line = line.split("[", 1)[0]
        if line:
            names.add(normalize_name(line))
    return names


def parse_lock_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise SystemExit(f"Lock file line is not pinned with ==: {raw_line}")
        name = line.split("==", 1)[0].strip()
        if name:
            names.add(normalize_name(name))
    return names


def main() -> None:
    if not REQUIREMENTS.exists():
        raise SystemExit(f"Missing {REQUIREMENTS}")
    if not LOCK.exists():
        raise SystemExit(f"Missing {LOCK}")
    direct_names = parse_requirement_names(REQUIREMENTS)
    lock_names = parse_lock_names(LOCK)
    missing = sorted(direct_names - lock_names)
    if missing:
        raise SystemExit("Missing direct requirements in lock file: " + ", ".join(missing))
    print(f"requirements lock ok: {len(direct_names)} direct packages, {len(lock_names)} locked packages")


if __name__ == "__main__":
    main()
