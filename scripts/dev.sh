#!/usr/bin/env bash
# Start the backend (port 8000) and the frontend dev server (port 5173) together.
# Open http://localhost:5173 in your browser. Press Ctrl+C to stop both.
#
# Needs Python 3.11+, Node.js 20+ and ffmpeg (for audio files).
# Jobs run inside the backend process here; Docker uses a separate worker + Redis.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v ffmpeg >/dev/null; then
  echo "Note: ffmpeg is not installed, so audio uploads won't work (MIDI will)."
  echo "      macOS: brew install ffmpeg · Ubuntu: sudo apt install ffmpeg · Windows: winget install ffmpeg"
fi
if [ ! -d backend/.venv ]; then
  echo "Setting up Python environment (first run only, downloads PyTorch, can take a while)…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -e "backend[dev,audio,separation]"
  backend/.venv/bin/pip install -q --no-deps basic-pitch==0.4.0
fi
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages (first run only)…"
  (cd frontend && npm install)
fi

(cd backend && .venv/bin/uvicorn tabiffy.api:app --reload --reload-dir tabiffy --port 8000) &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null' EXIT
cd frontend && npm run dev
