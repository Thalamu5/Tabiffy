#!/usr/bin/env bash
# Start the backend (port 8000) and the frontend dev server (port 5173) together.
# Open http://localhost:5173 in your browser. Press Ctrl+C to stop both.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d backend/.venv ]; then
  echo "Setting up Python environment (first run only)…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -e "backend[dev]"
fi
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages (first run only)…"
  (cd frontend && npm install)
fi

(cd backend && .venv/bin/uvicorn tabiffy.api:app --reload --port 8000) &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null' EXIT
cd frontend && npm run dev
