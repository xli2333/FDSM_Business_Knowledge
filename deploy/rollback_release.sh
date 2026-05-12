#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/fdsm/app}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"
PROJECT_PREFIX="${PROJECT_PREFIX:-fdsmarticles-prod}"
ACTIVE_FILE="${ACTIVE_FILE:-$APP_DIR/.active_color}"
COMPOSE_SERVICES="${COMPOSE_SERVICES:-redis backend-web frontend}"
SWITCH_NGINX="${SWITCH_NGINX:-1}"
STOP_FAILED_AFTER_ROLLBACK="${STOP_FAILED_AFTER_ROLLBACK:-0}"
NGINX_CONFIG="${NGINX_CONFIG:-/etc/nginx/sites-available/fdsmarticles.conf}"

fail() {
  echo "[rollback] $*" >&2
  exit 1
}

port_for_color() {
  case "$1" in
    blue) echo "$BLUE_PORT" ;;
    green) echo "$GREEN_PORT" ;;
    *) fail "unsupported color: $1" ;;
  esac
}

project_for_color() {
  echo "${PROJECT_PREFIX}-$1"
}

wait_for_http() {
  local url="$1"
  local attempts="${2:-45}"
  local delay="${3:-2}"
  local index
  for index in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

switch_nginx_to_port() {
  local target_port="$1"
  [ "$(id -u)" -eq 0 ] || fail "SWITCH_NGINX=1 requires root or sudo"
  [ -f "$NGINX_CONFIG" ] || fail "nginx config not found: $NGINX_CONFIG"
  command -v nginx >/dev/null || fail "nginx command not found"
  command -v systemctl >/dev/null || fail "systemctl command not found"

  local backup_path="${NGINX_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$NGINX_CONFIG" "$backup_path"
  perl -0pi -e "s/server 127\\.0\\.0\\.1:\\d+;/server 127.0.0.1:${target_port};/g" "$NGINX_CONFIG"
  if ! nginx -t; then
    cp "$backup_path" "$NGINX_CONFIG"
    nginx -t || true
    fail "nginx config validation failed; restored $backup_path"
  fi
  systemctl reload nginx
  echo "[rollback] nginx now points to 127.0.0.1:${target_port}"
}

[ -d "$APP_DIR" ] || fail "APP_DIR not found: $APP_DIR"
[ -f "$ENV_FILE" ] || fail "ENV_FILE not found: $ENV_FILE"
[ -f "$COMPOSE_FILE" ] || fail "COMPOSE_FILE not found: $COMPOSE_FILE"
command -v docker >/dev/null || fail "docker command not found"
command -v curl >/dev/null || fail "curl command not found"

cd "$APP_DIR"
set -a
# shellcheck disable=SC1090
. <(sed -e '1s/^\xEF\xBB\xBF//' -e 's/\r$//' "$ENV_FILE")
set +a

BLUE_PORT="${BLUE_PORT:-${APP_PORT:-8080}}"
GREEN_PORT="${GREEN_PORT:-8081}"
ACTIVE_COLOR="${ACTIVE_COLOR:-$(cat "$ACTIVE_FILE" 2>/dev/null || echo blue)}"
case "$ACTIVE_COLOR" in
  blue|green) ;;
  *) fail "active color must be blue or green, got $ACTIVE_COLOR" ;;
esac

if [ -n "${ROLLBACK_COLOR:-}" ]; then
  case "$ROLLBACK_COLOR" in
    blue|green) ;;
    *) fail "rollback color must be blue or green, got $ROLLBACK_COLOR" ;;
  esac
else
  if [ "$ACTIVE_COLOR" = "blue" ]; then
    ROLLBACK_COLOR="green"
  else
    ROLLBACK_COLOR="blue"
  fi
fi

ROLLBACK_PORT="$(port_for_color "$ROLLBACK_COLOR")"
ROLLBACK_PROJECT="$(project_for_color "$ROLLBACK_COLOR")"
FAILED_PROJECT="$(project_for_color "$ACTIVE_COLOR")"
ROLLBACK_BASE_URL="${ROLLBACK_BASE_URL:-http://127.0.0.1:${ROLLBACK_PORT}}"

echo "[rollback] active=$ACTIVE_COLOR rollback=$ROLLBACK_COLOR port=$ROLLBACK_PORT project=$ROLLBACK_PROJECT"
APP_PORT="$ROLLBACK_PORT" docker compose -p "$ROLLBACK_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build $COMPOSE_SERVICES
wait_for_http "$ROLLBACK_BASE_URL/healthz" "${HEALTH_WAIT_ATTEMPTS:-45}" "${HEALTH_WAIT_DELAY_SECONDS:-2}" || fail "rollback healthz did not become ready"
curl -fsS "$ROLLBACK_BASE_URL/api/health?details=1" >/dev/null

if [ "$SWITCH_NGINX" = "1" ]; then
  switch_nginx_to_port "$ROLLBACK_PORT"
  echo "$ROLLBACK_COLOR" > "$ACTIVE_FILE"
else
  echo "[rollback] rollback stack is healthy but nginx was not switched."
fi

if [ "$STOP_FAILED_AFTER_ROLLBACK" = "1" ]; then
  APP_PORT="$(port_for_color "$ACTIVE_COLOR")" docker compose -p "$FAILED_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down --remove-orphans || true
fi

echo "[rollback] active color is now $ROLLBACK_COLOR"
