#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

uv sync
uv run alembic upgrade head

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

(
  cd frontend
  if [[ ! -d node_modules ]]; then npm install; fi
  npm run dev
) &
FRONTEND_PID=$!

echo "后端: http://127.0.0.1:8000"
echo "前端: http://127.0.0.1:5173"
wait
