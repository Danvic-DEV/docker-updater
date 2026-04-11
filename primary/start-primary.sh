#!/usr/bin/env bash
set -euo pipefail

export POSTGRES_USER="${POSTGRES_USER:-docker_updater}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-docker_updater}"
export POSTGRES_DB="${POSTGRES_DB:-docker_updater}"
export PGDATA="${PGDATA:-/config}"

mkdir -p /config

docker-entrypoint.sh postgres &
PG_PID=$!

for _ in $(seq 1 60); do
  if pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
  echo "Postgres did not become ready in time" >&2
  exit 1
fi

export APP_ENV="${APP_ENV:-dev}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}}"

cd /workspace/primary-api

# Agent API on port 58000 (exposed)
python -m uvicorn app.main:app --host 0.0.0.0 --port 58000 &
AGENT_API_PID=$!

# Admin API on port 8001 (not exposed)
python -m uvicorn app.main:admin_app --host 127.0.0.1 --port 8001 &
ADMIN_API_PID=$!

cd /workspace/primary-web
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:58000}"
npm run dev -- --host 0.0.0.0 --port 5173 &
WEB_PID=$!

cd /workspace/agent
LOCAL_AGENT_PID=""
if [[ "${PRIMARY_EMBEDDED_AGENT_ENABLE:-true}" == "true" ]]; then
  export AGENT_ID="${PRIMARY_EMBEDDED_AGENT_ID:-primary-local-agent}"
  export AGENT_NAME="${PRIMARY_EMBEDDED_AGENT_NAME:-Primary Local Agent}"
  export PRIMARY_API_BASE_URL="${PRIMARY_EMBEDDED_AGENT_API_BASE_URL:-http://127.0.0.1:58000}"
  export POLL_INTERVAL_SECONDS="${PRIMARY_EMBEDDED_AGENT_POLL_INTERVAL_SECONDS:-5}"

  python -m app.main &
  LOCAL_AGENT_PID=$!
fi

cleanup() {
  if [[ -n "$LOCAL_AGENT_PID" ]]; then
    kill "$LOCAL_AGENT_PID" >/dev/null 2>&1 || true
  fi
  kill "$WEB_PID" "$ADMIN_API_PID" "$AGENT_API_PID" "$PG_PID" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

if [[ -n "$LOCAL_AGENT_PID" ]]; then
  wait -n "$LOCAL_AGENT_PID" "$WEB_PID" "$ADMIN_API_PID" "$AGENT_API_PID" "$PG_PID"
else
  wait -n "$WEB_PID" "$ADMIN_API_PID" "$AGENT_API_PID" "$PG_PID"
fi
exit 1

