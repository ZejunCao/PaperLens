#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -f .env ]] && grep -E '^[[:space:]]*PAPERLENS_PARSER=pymupdf([[:space:]]|$)' .env >/dev/null 2>&1; then
  uv sync
else
  uv sync --extra mineru
fi
uv run alembic upgrade head

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

(
  cd frontend
  if [[ ! -d node_modules ]]; then npm install; fi
  npm run dev
) &
FRONTEND_PID=$!

echo "后端: http://0.0.0.0:8000"
echo "前端: http://0.0.0.0:5173"
wait
