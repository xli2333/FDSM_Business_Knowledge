from __future__ import annotations

import json

from backend.database import collect_database_diagnostics


def main() -> None:
    diagnostics = collect_database_diagnostics(include_writable_probe=True)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
