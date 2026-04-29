#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv. Create it with: python3 -m venv .venv"
  echo "Then install deps with: .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! .venv/bin/python -c "import flask, flask_session, certifi" >/dev/null 2>&1; then
  echo "The local .venv looks unhealthy."
  echo "Rebuild it with:"
  echo "  mv .venv .venv_broken_\$(date +%Y%m%d_%H%M%S)"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install -r requirements.txt"
  exit 1
fi

export FLASK_APP=app.py
export FLASK_SESSION_SECRET_KEY="${FLASK_SESSION_SECRET_KEY:-local-dev-session-secret}"
PORT="${PORT:-5001}"
HOST="${HOST:-127.0.0.1}"

if command -v lsof >/dev/null 2>&1; then
  existing_pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$existing_pids" ]]; then
    echo "Stopping existing listener(s) on port $PORT: $existing_pids"
    kill $existing_pids 2>/dev/null || true
    sleep 1

    stubborn_pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$stubborn_pids" ]]; then
      echo "Force-stopping listener(s) still using port $PORT: $stubborn_pids"
      kill -9 $stubborn_pids
      sleep 1
    fi
  fi
fi

exec .venv/bin/python -m flask run --host "$HOST" --port "$PORT"
