from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.topic_engine import auto_generate_topics


def main() -> None:
    args = [item for item in sys.argv[1:] if not item.startswith("--")]
    limit = int(args[0]) if args else 6
    result = auto_generate_topics(limit=limit)
    print(result)


if __name__ == "__main__":
    main()
