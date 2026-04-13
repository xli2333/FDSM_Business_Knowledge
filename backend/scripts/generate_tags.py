from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.tag_engine import generate_tags_for_articles


def main() -> None:
    args = [item for item in sys.argv[1:] if not item.startswith("--")]
    limit = int(args[0]) if args else 50
    regenerate = "--regenerate" in sys.argv[1:]
    result = generate_tags_for_articles(limit=limit, regenerate=regenerate)
    print(result)


if __name__ == "__main__":
    main()
