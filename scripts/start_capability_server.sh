#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

CAPABILITY_SERVER_HOST="${CAPABILITY_SERVER_HOST:-127.0.0.1}"
CAPABILITY_SERVER_PORT="${CAPABILITY_SERVER_PORT:-8787}"

echo "Starting capability stack on http://${CAPABILITY_SERVER_HOST}:${CAPABILITY_SERVER_PORT}"
cd "$PROJECT_DIR"
uv run python -m capabilities.server --host "$CAPABILITY_SERVER_HOST" --port "$CAPABILITY_SERVER_PORT"
