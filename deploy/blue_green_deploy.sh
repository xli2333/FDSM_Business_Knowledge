#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/fdsm/app}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"
PROJECT_PREFIX="${PROJECT_PREFIX:-fdsmarticles-prod}"
ACTIVE_FILE="${ACTIVE_FILE:-$APP_DIR/.active_color}"
COMPOSE_SERVICES="${COMPOSE_SERVICES:-redis backend-web frontend}"
SWITCH_NGINX="${SWITCH_NGINX:-0}"
STOP_OLD_AFTER_SWITCH="${STOP_OLD_AFTER_SWITCH:-0}"
NGINX_CONFIG="${NGINX_CONFIG:-/etc/nginx/sites-available/fdsmarticles.conf}"
SCHEMA_CHANGE_GUARD="${SCHEMA_CHANGE_GUARD:-1}"
SCHEMA_CHANGE_REQUIRED="${SCHEMA_CHANGE_REQUIRED:-0}"
SCHEMA_CHANGE_BASE_REF="${SCHEMA_CHANGE_BASE_REF:-}"
ALLOW_SCHEMA_BLUE_GREEN="${ALLOW_SCHEMA_BLUE_GREEN:-0}"

fail() {
  echo "[blue-green] $*" >&2
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

probe_candidate() {
  local base_url="$1"
  echo "[blue-green] probing $base_url"
  curl -fsS "$base_url/healthz" >/dev/null
  curl -fsS "$base_url/api/health?details=1" >/dev/null
  curl -fsS "$base_url/api/home/feed?language=zh" >/dev/null
  local debug_code
  debug_code="$(curl -sS -o /dev/null -w "%{http_code}" -H "X-Debug-User-Id: qa" "$base_url/api/auth/status" || true)"
  [ "$debug_code" = "400" ] || fail "debug header probe expected 400, got $debug_code"
}

schema_change_detected() {
  if [ "$SCHEMA_CHANGE_REQUIRED" = "1" ]; then
    return 0
  fi

  if [ -z "$SCHEMA_CHANGE_BASE_REF" ]; then
    return 1
  fi
  command -v git >/dev/null || return 1
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1

  local changed_files
  changed_files="$(git diff --name-only "$SCHEMA_CHANGE_BASE_REF"...HEAD -- backend 2>/dev/null || true)"
  if printf '%s\n' "$changed_files" | grep -Eiq '(^backend/database\.py$|(^|/)(schema|schemas|migration|migrations)(/|\.|$))'; then
    return 0
  fi

  local changed_diff
  changed_diff="$(git diff --unified=0 "$SCHEMA_CHANGE_BASE_REF"...HEAD -- backend 2>/dev/null || true)"
  if printf '%s\n' "$changed_diff" | grep -Eiq '^\+.*(ensure_runtime_tables|CREATE[[:space:]]+TABLE|ALTER[[:space:]]+TABLE|DROP[[:space:]]+TABLE|CREATE[[:space:]]+INDEX|DROP[[:space:]]+INDEX)'; then
    return 0
  fi
  return 1
}

enforce_schema_change_guard() {
  if [ "$SCHEMA_CHANGE_GUARD" != "1" ]; then
    return
  fi
  if ! schema_change_detected; then
    return
  fi
  if [ "$ALLOW_SCHEMA_BLUE_GREEN" = "1" ]; then
    echo "[blue-green] schema change detected but ALLOW_SCHEMA_BLUE_GREEN=1; continuing by operator override" >&2
    return
  fi
  fail "schema change detected; shared SQLite blue-green candidates may lock the active stack. Use maintenance deployment or set ALLOW_SCHEMA_BLUE_GREEN=1 after manual review."
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
  echo "[blue-green] nginx now points to 127.0.0.1:${target_port}"
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

enforce_schema_change_guard

if [ -n "${CANDIDATE_COLOR:-}" ]; then
  case "$CANDIDATE_COLOR" in
    blue|green) ;;
    *) fail "candidate color must be blue or green, got $CANDIDATE_COLOR" ;;
  esac
else
  if [ "$ACTIVE_COLOR" = "blue" ]; then
    CANDIDATE_COLOR="green"
  else
    CANDIDATE_COLOR="blue"
  fi
fi

CANDIDATE_PORT="$(port_for_color "$CANDIDATE_COLOR")"
CANDIDATE_PROJECT="$(project_for_color "$CANDIDATE_COLOR")"
ACTIVE_PROJECT="$(project_for_color "$ACTIVE_COLOR")"
CANDIDATE_BASE_URL="${CANDIDATE_BASE_URL:-http://127.0.0.1:${CANDIDATE_PORT}}"
success=0

cleanup_on_failure() {
  if [ "$success" != "1" ]; then
    echo "[blue-green] candidate failed; cleaning $CANDIDATE_PROJECT" >&2
    APP_PORT="$CANDIDATE_PORT" docker compose -p "$CANDIDATE_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down --remove-orphans || true
  fi
}
trap cleanup_on_failure EXIT

echo "[blue-green] active=$ACTIVE_COLOR candidate=$CANDIDATE_COLOR port=$CANDIDATE_PORT project=$CANDIDATE_PROJECT"
APP_PORT="$CANDIDATE_PORT" docker compose -p "$CANDIDATE_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build $COMPOSE_SERVICES
wait_for_http "$CANDIDATE_BASE_URL/healthz" "${HEALTH_WAIT_ATTEMPTS:-45}" "${HEALTH_WAIT_DELAY_SECONDS:-2}" || fail "candidate healthz did not become ready"
probe_candidate "$CANDIDATE_BASE_URL"

if [ "$SWITCH_NGINX" = "1" ]; then
  switch_nginx_to_port "$CANDIDATE_PORT"
  echo "$CANDIDATE_COLOR" > "$ACTIVE_FILE"
  if [ "$STOP_OLD_AFTER_SWITCH" = "1" ]; then
    APP_PORT="$(port_for_color "$ACTIVE_COLOR")" docker compose -p "$ACTIVE_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down --remove-orphans || true
  fi
  echo "[blue-green] switched active color to $CANDIDATE_COLOR"
else
  echo "[blue-green] candidate is healthy but nginx was not switched."
  echo "[blue-green] switch command: sudo SWITCH_NGINX=1 ACTIVE_COLOR=$ACTIVE_COLOR CANDIDATE_COLOR=$CANDIDATE_COLOR bash deploy/blue_green_deploy.sh"
fi

success=1
