from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import ensure_database_ready


def main() -> None:
    force_rebuild = "--rebuild" in sys.argv[1:]
    ensure_database_ready(force_rebuild=force_rebuild)
    print({"database_ready": True, "force_rebuild": force_rebuild})


if __name__ == "__main__":
    main()
