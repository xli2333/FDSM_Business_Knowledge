from __future__ import annotations

from backend.services.async_task_service import queue_healthcheck


if __name__ == "__main__":
    queue_healthcheck()
    print("worker ok")
