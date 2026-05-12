#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/fdsm/app}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"

echo "[preflight] app dir: $APP_DIR"

fail() {
  echo "[preflight] $*" >&2
  exit 1
}

command -v docker >/dev/null
docker compose version >/dev/null

test -f "$ENV_FILE"
test -f "$COMPOSE_FILE"
test -f "$APP_DIR/Dockerfile.backend"
test -f "$APP_DIR/Dockerfile.backup"
test -f "$APP_DIR/requirements.lock.txt"
test -f "$APP_DIR/frontend/Dockerfile"
test -f "$APP_DIR/deploy/backup_sqlite.py"
test -f "$APP_DIR/deploy/restore_sqlite_backup.py"
test -f "$APP_DIR/deploy/bootstrap_https.sh"
test -f "$APP_DIR/deploy/blue_green_deploy.sh"
test -f "$APP_DIR/deploy/rollback_release.sh"

set -a
# shellcheck disable=SC1090
. <(sed -e '1s/^\xEF\xBB\xBF//' -e 's/\r$//' "$ENV_FILE")
set +a

if [ "${APP_ENV:-}" != "production" ]; then
  fail "APP_ENV must be production"
fi

if [ -z "${SITE_BASE_URL:-}" ] || [[ "${SITE_BASE_URL:-}" != https://* ]]; then
  fail "SITE_BASE_URL must be the final HTTPS origin"
fi

if [[ "${SITE_BASE_URL:-}" == *"knowledge.example.edu"* ]] || [[ "${ALLOWED_ORIGINS:-}" == *"knowledge.example.edu"* ]]; then
  fail "replace knowledge.example.edu placeholders before production"
fi

if [ -z "${ALLOWED_ORIGINS:-}" ] || [[ ",${ALLOWED_ORIGINS}," == *",*,"* ]]; then
  fail "ALLOWED_ORIGINS must be an explicit whitelist"
fi

if [ "${DEV_AUTH_ENABLED:-0}" != "0" ] || [ "${VITE_ENABLE_DEBUG_AUTH:-0}" != "0" ]; then
  fail "debug auth must stay disabled in production"
fi

if [ "${METRICS_ENABLED:-1}" != "0" ] && [ -z "${METRICS_TOKEN:-}" ]; then
  fail "METRICS_TOKEN is required when metrics are enabled in production"
fi
case "${METRICS_TOKEN:-}" in
  ""|replace-with-a-long-random-metrics-token|change-me)
    if [ "${METRICS_ENABLED:-1}" != "0" ]; then
      fail "METRICS_TOKEN must be a real production secret"
    fi
    ;;
esac

if [ "${SENTRY_REQUIRED:-0}" = "1" ] && [ -z "${SENTRY_DSN:-}" ]; then
  fail "SENTRY_DSN is required when SENTRY_REQUIRED=1"
fi

case "${REDIS_PASSWORD:-}" in
  ""|fdsm-local-redis-pass|change-me|replace-with-a-long-random-redis-password)
    fail "REDIS_PASSWORD must be a real production secret"
    ;;
esac
if [ "${#REDIS_PASSWORD}" -lt 16 ]; then
  fail "REDIS_PASSWORD must be at least 16 characters"
fi

case "${AUTH_BACKEND:-cas}" in
  cas|auto|dual|supabase)
    ;;
  *)
    fail "AUTH_BACKEND must be one of cas, auto, dual, supabase"
    ;;
esac

if [ "${ALLOW_LEGACY_SUPABASE_AUTH:-0}" != "1" ]; then
  case "${AUTH_BACKEND:-cas}" in
    supabase|dual)
      fail "AUTH_BACKEND=supabase/dual requires ALLOW_LEGACY_SUPABASE_AUTH=1 for controlled rollback"
      ;;
  esac
  if [ -n "${SUPABASE_URL:-}" ] || [ -n "${SUPABASE_ANON_KEY:-}" ]; then
    fail "SUPABASE_URL and SUPABASE_ANON_KEY must stay empty unless ALLOW_LEGACY_SUPABASE_AUTH=1"
  fi
fi

if [ "${ALLOW_LEGACY_SUPABASE_AUTH:-0}" = "1" ]; then
  case "${AUTH_BACKEND:-cas}" in
    supabase|dual)
      [ -n "${SUPABASE_URL:-}" ] || fail "SUPABASE_URL is required when legacy Supabase auth rollback is enabled"
      [ -n "${SUPABASE_ANON_KEY:-}" ] || fail "SUPABASE_ANON_KEY is required when legacy Supabase auth rollback is enabled"
      ;;
  esac
fi

if [ "${CAS_ENABLED:-1}" = "1" ]; then
  [ -n "${CAS_SERVER_URL:-}" ] || fail "CAS_SERVER_URL is required"
  [ -n "${CAS_SERVICE_BASE_URL:-}" ] || fail "CAS_SERVICE_BASE_URL is required"
  [[ "${CAS_SERVICE_BASE_URL:-}" == https://* ]] || fail "CAS_SERVICE_BASE_URL must be HTTPS"
fi

if [ "${BACKUP_OFFSITE_REQUIRED:-0}" = "1" ] && [ -z "${BACKUP_OFFSITE_TARGET:-}" ]; then
  fail "BACKUP_OFFSITE_TARGET is required when BACKUP_OFFSITE_REQUIRED=1"
fi

case "${BACKUP_OFFSITE_TARGET:-}" in
  ""|change-me|replace-me|file:///tmp/*)
    if [ "${BACKUP_OFFSITE_REQUIRED:-0}" = "1" ]; then
      fail "BACKUP_OFFSITE_TARGET must be a real offsite target"
    fi
    ;;
esac

if [ "${BACKUP_ENCRYPTION_REQUIRED:-0}" = "1" ] && [ -z "${BACKUP_ENCRYPTION_RECIPIENT:-}" ]; then
  fail "BACKUP_ENCRYPTION_RECIPIENT is required when BACKUP_ENCRYPTION_REQUIRED=1"
fi

case "${BACKUP_ENCRYPTION_RECIPIENT:-}" in
  ""|change-me|replace-me)
    if [ "${BACKUP_ENCRYPTION_REQUIRED:-0}" = "1" ]; then
      fail "BACKUP_ENCRYPTION_RECIPIENT must be a real GPG recipient"
    fi
    ;;
esac

if command -v stat >/dev/null && [[ "$(uname -s 2>/dev/null || true)" != MINGW* ]] && [[ "$(uname -s 2>/dev/null || true)" != MSYS* ]] && [[ "$(uname -s 2>/dev/null || true)" != CYGWIN* ]]; then
  env_mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)"
  if [ -n "$env_mode" ] && [ $((8#$env_mode & 007)) -ne 0 ]; then
    fail ".env.production must not be world-readable; run chmod 640 or chmod 600"
  fi
fi

mkdir -p "$APP_DIR/data" "$APP_DIR/backups" "$APP_DIR/logs"

if [ ! -f "$APP_DIR/data/fudan_knowledge_base.db" ]; then
  fail "missing data/fudan_knowledge_base.db"
fi

if [ ! -d "$APP_DIR/data/Fudan_Business_Knowledge_Data" ]; then
  fail "missing data/Fudan_Business_Knowledge_Data"
fi

if [ ! -d "$APP_DIR/data/faiss_index_business" ]; then
  fail "missing data/faiss_index_business"
fi

if command -v df >/dev/null; then
  df -h "$APP_DIR"
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null

echo "[preflight] ok"
