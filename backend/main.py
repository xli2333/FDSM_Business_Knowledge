from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.config import (
    ALLOWED_ORIGINS,
    APP_ENV,
    APP_TITLE,
    ASYNC_TASKS_ENABLED,
    AUDIO_DIR,
    DATA_DIR,
    EDITORIAL_UPLOADS_DIR,
    IS_PRODUCTION,
    MEDIA_UPLOADS_DIR,
    METRICS_ENABLED,
    METRICS_TOKEN,
    REQUEST_LOG_JSON_ENABLED,
    SENTRY_DSN,
    SENTRY_TRACES_SAMPLE_RATE,
)
from backend.database import collect_database_diagnostics, database_is_ready, ensure_database_ready, ensure_runtime_tables
from backend.routers.analytics import router as analytics_router
from backend.routers.admin import router as admin_router
from backend.routers.auth import router as auth_router
from backend.routers.articles import router as articles_router
from backend.routers.billing import router as billing_router
from backend.routers.cas_auth import router as cas_auth_router
from backend.routers.chat import router as chat_router
from backend.routers.columns import router as columns_router
from backend.routers.commerce import router as commerce_router
from backend.routers.editorial import router as editorial_router
from backend.routers.follows import router as follows_router
from backend.routers.home import router as home_router
from backend.routers.media import router as media_router
from backend.routers.me import router as me_router
from backend.routers.membership import router as membership_router
from backend.routers.organizations import router as organizations_router
from backend.routers.publishing import router as publishing_router
from backend.routers.search import router as search_router
from backend.routers.tags import router as tags_router
from backend.routers.time_machine import router as time_machine_router
from backend.routers.topics import router as topics_router
from backend.routers.user_knowledge import router as user_knowledge_router

from backend.services.media_service import sync_local_audio_library


if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=APP_ENV,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )


def _prepare_runtime() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    EDITORIAL_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    state_key = hashlib.sha1(str(DATA_DIR.resolve()).encode("utf-8")).hexdigest()[:16]
    state_dir = Path(tempfile.gettempdir()) / f"fdsmarticles-{state_key}"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "startup.lock"
    sentinel_path = state_dir / "startup.done"

    with _exclusive_startup_lock(lock_path):
        if sentinel_path.exists():
            return
        ensure_database_ready()
        ensure_runtime_tables()
        try:
            from backend.services.cas_auth_service import cleanup_expired_sessions

            cleanup_expired_sessions()
        except Exception as exc:
            print(f"[startup] cas session cleanup skipped: {exc}", flush=True)
        sync_local_audio_library()
        sentinel_path.write_text("ok", encoding="utf-8")


@contextmanager
def _exclusive_startup_lock(lock_path: Path):
    lock_file = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name != "nt":
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name != "nt":
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _prepare_runtime()
    yield


app = FastAPI(title=APP_TITLE, lifespan=lifespan)
audio_directory = AUDIO_DIR
_DEBUG_AUTH_HEADERS = {"x-debug-user-id", "x-debug-user-email"}
_PROCESS_STARTED_AT = time.time()
_METRICS_LOCK = threading.Lock()
_METRICS_REQUESTS: dict[tuple[str, str, int], int] = {}
_METRICS_LATENCY_SUM: dict[tuple[str, str, int], float] = {}
_METRICS_LATENCY_COUNT: dict[tuple[str, str, int], int] = {}
_METRICS_PATHS = {"/api/metrics"}


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))


def _observe_request(method: str, path: str, status_code: int, elapsed_seconds: float) -> None:
    if not METRICS_ENABLED:
        return
    key = (method, path, status_code)
    with _METRICS_LOCK:
        _METRICS_REQUESTS[key] = _METRICS_REQUESTS.get(key, 0) + 1
        _METRICS_LATENCY_SUM[key] = _METRICS_LATENCY_SUM.get(key, 0.0) + elapsed_seconds
        _METRICS_LATENCY_COUNT[key] = _METRICS_LATENCY_COUNT.get(key, 0) + 1


def _escape_metric_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _render_metrics() -> str:
    with _METRICS_LOCK:
        request_rows = list(_METRICS_REQUESTS.items())
        latency_sum_rows = list(_METRICS_LATENCY_SUM.items())
        latency_count_rows = list(_METRICS_LATENCY_COUNT.items())

    lines = [
        "# HELP fdsm_http_requests_total Total HTTP requests handled by the backend.",
        "# TYPE fdsm_http_requests_total counter",
    ]
    for (method, path, status_code), count in sorted(request_rows):
        lines.append(
            'fdsm_http_requests_total{method="%s",path="%s",status="%s"} %s'
            % (_escape_metric_label(method), _escape_metric_label(path), status_code, count)
        )
    lines.extend(
        [
            "# HELP fdsm_http_request_duration_seconds_sum Sum of backend HTTP request durations.",
            "# TYPE fdsm_http_request_duration_seconds_sum counter",
        ]
    )
    for (method, path, status_code), value in sorted(latency_sum_rows):
        lines.append(
            'fdsm_http_request_duration_seconds_sum{method="%s",path="%s",status="%s"} %.6f'
            % (_escape_metric_label(method), _escape_metric_label(path), status_code, value)
        )
    lines.extend(
        [
            "# HELP fdsm_http_request_duration_seconds_count Count of backend HTTP request durations.",
            "# TYPE fdsm_http_request_duration_seconds_count counter",
        ]
    )
    for (method, path, status_code), count in sorted(latency_count_rows):
        lines.append(
            'fdsm_http_request_duration_seconds_count{method="%s",path="%s",status="%s"} %s'
            % (_escape_metric_label(method), _escape_metric_label(path), status_code, count)
        )
    lines.extend(
        [
            "# HELP fdsm_app_info Application metadata for this backend process.",
            "# TYPE fdsm_app_info gauge",
            'fdsm_app_info{env="%s",pid="%s"} 1'
            % (_escape_metric_label(APP_ENV), _escape_metric_label(str(os.getpid()))),
            "# HELP fdsm_app_process_start_time_seconds Unix timestamp when this backend process started.",
            "# TYPE fdsm_app_process_start_time_seconds gauge",
            "fdsm_app_process_start_time_seconds %.3f" % _PROCESS_STARTED_AT,
            "# HELP fdsm_app_uptime_seconds Backend process uptime in seconds.",
            "# TYPE fdsm_app_uptime_seconds gauge",
            "fdsm_app_uptime_seconds %.3f" % max(0.0, time.time() - _PROCESS_STARTED_AT),
        ]
    )
    return "\n".join(lines) + "\n"


def _metrics_request_authorized(request: Request) -> bool:
    if not METRICS_TOKEN:
        return True
    bearer = request.headers.get("authorization", "").strip()
    if bearer.lower().startswith("bearer "):
        if hmac.compare_digest(bearer[7:].strip(), METRICS_TOKEN):
            return True
    header_token = request.headers.get("x-metrics-token", "").strip()
    return hmac.compare_digest(header_token, METRICS_TOKEN)


def _is_metrics_path(path: str) -> bool:
    return path in _METRICS_PATHS


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip() or uuid.uuid4().hex
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = int(response.status_code)
        return response
    except Exception:
        status_code = 500
        raise
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        route_path = _route_label(request)
        if not _is_metrics_path(request.url.path):
            _observe_request(request.method, route_path, status_code, elapsed_seconds)
        try:
            response.headers["X-Request-Id"] = request_id
        except Exception:
            pass
        if REQUEST_LOG_JSON_ENABLED:
            log_payload = {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": route_path,
                "status": status_code,
                "latency_ms": int(elapsed_seconds * 1000),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent", ""),
                "forwarded_for": request.headers.get("x-forwarded-for", ""),
            }
            print(json.dumps(log_payload, ensure_ascii=False), flush=True)


@app.middleware("http")
async def reject_debug_auth_headers_in_production(request: Request, call_next):
    if IS_PRODUCTION and any(header in request.headers for header in _DEBUG_AUTH_HEADERS):
        return JSONResponse(
            status_code=400,
            content={"detail": "Debug auth headers are disabled in production."},
        )
    return await call_next(request)

if IS_PRODUCTION and not ALLOWED_ORIGINS:
    raise RuntimeError("ALLOWED_ORIGINS must be set to an explicit origin in production.")

_cors_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] if IS_PRODUCTION else ["*"]
_cors_headers = (
    ["Authorization", "Content-Type", "X-Requested-With", "X-CSRF-Token"]
    if IS_PRODUCTION
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if IS_PRODUCTION else (ALLOWED_ORIGINS or ["*"]),
    allow_credentials=True,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
)

if not IS_PRODUCTION:
    app.mount("/audio-files", StaticFiles(directory=audio_directory, check_dir=False), name="audio-files")
    app.mount("/editorial-uploads", StaticFiles(directory=EDITORIAL_UPLOADS_DIR, check_dir=False), name="editorial-uploads")
    app.mount("/media-uploads", StaticFiles(directory=MEDIA_UPLOADS_DIR, check_dir=False), name="media-uploads")

app.include_router(home_router)
app.include_router(auth_router)
app.include_router(cas_auth_router)
app.include_router(billing_router)
app.include_router(membership_router)
app.include_router(follows_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(me_router)
app.include_router(user_knowledge_router)
app.include_router(media_router)
app.include_router(organizations_router)
app.include_router(search_router)
app.include_router(articles_router)
app.include_router(tags_router)
app.include_router(columns_router)
app.include_router(topics_router)
app.include_router(chat_router)
app.include_router(time_machine_router)
app.include_router(commerce_router)
app.include_router(editorial_router)
app.include_router(publishing_router)


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": APP_TITLE,
        "environment": APP_ENV,
        "scope": "business-only",
    }


@app.get("/api/health")
def api_health_check(details: bool = False):
    db_ready = database_is_ready()
    diagnostics = None
    diagnostic_error = None
    if details:
        try:
            diagnostics = collect_database_diagnostics(include_writable_probe=True)
            db_ready = db_ready and diagnostics.get("quick_check") == "ok" and bool(diagnostics.get("writable_probe", {}).get("ok"))
        except Exception as exc:
            diagnostic_error = str(exc)
            db_ready = False
    content = {
        "status": "ok" if db_ready else "degraded",
        "service": APP_TITLE,
        "environment": APP_ENV,
        "database_ready": db_ready,
    }
    if diagnostics is not None:
        content["database"] = diagnostics
    if diagnostic_error:
        content["database_error"] = diagnostic_error
    return JSONResponse(
        status_code=200 if db_ready else 503,
        content=content,
    )


@app.get("/api/ready")
def api_readiness_check():
    db_ready = database_is_ready()
    queue_ready = True
    queue_error = None
    if ASYNC_TASKS_ENABLED:
        try:
            from backend.services.async_task_service import queue_healthcheck

            queue_healthcheck()
        except Exception as exc:
            queue_ready = False
            queue_error = str(exc)
    ready = db_ready and queue_ready
    content = {
        "status": "ok" if ready else "degraded",
        "service": APP_TITLE,
        "environment": APP_ENV,
        "database_ready": db_ready,
        "queue_ready": queue_ready,
    }
    if queue_error:
        content["queue_error"] = queue_error
    return JSONResponse(status_code=200 if ready else 503, content=content)


def _metrics_response(request: Request) -> PlainTextResponse:
    if not METRICS_ENABLED:
        return PlainTextResponse("metrics disabled\n", status_code=404)
    if not _metrics_request_authorized(request):
        _observe_request(request.method, request.url.path, 403, 0.0)
        return PlainTextResponse("forbidden\n", status_code=403)
    _observe_request(request.method, request.url.path, 200, 0.0)
    return PlainTextResponse(_render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/metrics")
def api_metrics(request: Request):
    return _metrics_response(request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
