#!/usr/bin/env bash
# start_mac.sh
# ------------------------------------------------------------
# macOS development launcher for BSE_data
# 1. Create/use a local Python virtual environment
# 2. Install Python and frontend dependencies when needed
# 3. Launch FastAPI, React/Vite, and Streamlit together
# ------------------------------------------------------------

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
FRONTEND_DIR="$ROOT_DIR/frontend"
REQUIREMENTS_FILE="$ROOT_DIR/backend/requirements.txt"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
START_BACKEND="${START_BACKEND:-1}"
START_FRONTEND="${START_FRONTEND:-1}"
START_STREAMLIT="${START_STREAMLIT:-1}"

cd "$ROOT_DIR"

log() {
  printf '[start_mac] %s\n' "$1"
}

fail() {
  printf '[start_mac] ERROR: %s\n' "$1" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

PYTHON_BIN="${BSE_PYTHON_BIN:-}"

if [ -n "$PYTHON_BIN" ] && ! command_exists "$PYTHON_BIN"; then
  fail "BSE_PYTHON_BIN points to '$PYTHON_BIN', but that executable was not found."
fi

for candidate in ${PYTHON_BIN:+"$PYTHON_BIN"} python3.13 python3.12 python3.11 python3 python; do
  if command_exists "$candidate"; then
    CANDIDATE_VERSION="$("$candidate" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

    case "$CANDIDATE_VERSION" in
      3.11|3.12|3.13|3.14|3.15|3.16|3.17|3.18|3.19)
        PYTHON_BIN="$candidate"
        PYTHON_VERSION="$CANDIDATE_VERSION"
        break
        ;;
    esac
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  fail "Python 3.11+ is required. Install it with: brew install python@3.12"
fi

log "Using $PYTHON_BIN (Python $PYTHON_VERSION)"

if [ ! -d "$VENV_DIR" ]; then
  log "Creating Python virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

log "Installing Python dependencies"
python -m pip install --upgrade pip
python -m pip install -r "$REQUIREMENTS_FILE"

if [ "$START_FRONTEND" = "1" ] && [ -d "$FRONTEND_DIR" ]; then
  if ! command_exists npm; then
    fail "npm is required for the React frontend. Install Node.js 18+ from https://nodejs.org/ or Homebrew."
  fi

  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    log "Installing frontend dependencies"
    npm --prefix "$FRONTEND_DIR" install
  fi
fi

PIDS=()

cleanup() {
  log "Stopping services"
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup EXIT INT TERM

if [ "$START_BACKEND" = "1" ]; then
  log "Starting FastAPI backend on http://localhost:$BACKEND_PORT"
  python -m uvicorn backend.server.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT" &
  PIDS+=("$!")
fi

if [ "$START_FRONTEND" = "1" ] && [ -d "$FRONTEND_DIR" ]; then
  log "Starting React frontend on http://localhost:$FRONTEND_PORT"
  npm --prefix "$FRONTEND_DIR" run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" &
  PIDS+=("$!")
fi

if [ "$START_STREAMLIT" = "1" ] && [ -f "$ROOT_DIR/app.py" ]; then
  log "Starting Streamlit control panel on http://localhost:$STREAMLIT_PORT"
  python -m streamlit run "$ROOT_DIR/app.py" --server.port "$STREAMLIT_PORT" &
  PIDS+=("$!")
fi

if [ "${#PIDS[@]}" -eq 0 ]; then
  fail "No services were selected. Enable at least one of START_BACKEND, START_FRONTEND, or START_STREAMLIT."
fi

log "Selected services started. Press Ctrl-C to stop."

wait
