#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/fdsm/app}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"

set -a
# shellcheck disable=SC1090
. <(sed -e '1s/^\xEF\xBB\xBF//' -e 's/\r$//' "$ENV_FILE")
set +a

LOCAL_BASE_URL="${LOCAL_BASE_URL:-http://127.0.0.1:${APP_PORT:-8080}}"

echo "[acceptance] docker services"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo "[acceptance] frontend healthz"
curl -fsS "$LOCAL_BASE_URL/healthz" >/dev/null

echo "[acceptance] api health details"
curl -fsS "$LOCAL_BASE_URL/api/health?details=1" >/dev/null

echo "[acceptance] public feed"
curl -fsS "$LOCAL_BASE_URL/api/home/feed?language=zh" >/dev/null

echo "[acceptance] debug headers rejected"
DEBUG_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -H "X-Debug-User-Id: qa" "$LOCAL_BASE_URL/api/auth/status")
test "$DEBUG_CODE" = "400"

echo "[acceptance] CAS login endpoint"
CAS_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -I "$LOCAL_BASE_URL/api/auth/cas/login?redirect=/admin" || true)
if [ "${CAS_ENABLED:-0}" = "1" ]; then
  test "$CAS_CODE" = "302" || test "$CAS_CODE" = "307"
else
  test "$CAS_CODE" = "503"
fi

echo "[acceptance] db diagnostics"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-web python -m backend.scripts.db_diagnostics >/dev/null

echo "[acceptance] worker healthcheck"
if [ "${ACCEPTANCE_SKIP_WORKER:-0}" = "1" ]; then
  echo "[acceptance] worker healthcheck skipped"
else
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-worker python -m backend.worker_healthcheck
fi

echo "[acceptance] ok"
