from __future__ import annotations

from backend.database import ensure_database_ready, ensure_runtime_tables
from backend.services.async_task_service import run_worker_loop


def main() -> None:
    ensure_database_ready()
    ensure_runtime_tables()
    run_worker_loop()


if __name__ == "__main__":
    main()
