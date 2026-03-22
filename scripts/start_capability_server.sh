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
CAPABILITY_REAL_BACKEND="${CAPABILITY_REAL_BACKEND:-0}"
PERCEPTION_BACKEND="${PERCEPTION_BACKEND:-}"
PERCEPTION_DETECTIONS_PATH="${PERCEPTION_DETECTIONS_PATH:-}"
DETECTOR_BACKEND="${DETECTOR_BACKEND:-}"
DETECTOR_URL="${DETECTOR_URL:-}"

EXTRA_ARGS=()
if [[ "$CAPABILITY_REAL_BACKEND" == "1" || "$CAPABILITY_REAL_BACKEND" == "true" || "$CAPABILITY_REAL_BACKEND" == "yes" ]]; then
    EXTRA_ARGS+=(--real-backend)
    echo "Starting capability stack in real-backend mode on http://${CAPABILITY_SERVER_HOST}:${CAPABILITY_SERVER_PORT}"
else
    echo "Starting capability stack in mock mode on http://${CAPABILITY_SERVER_HOST}:${CAPABILITY_SERVER_PORT}"
fi
if [ -n "$PERCEPTION_BACKEND" ]; then
    echo "Perception backend override: $PERCEPTION_BACKEND"
fi
if [ -n "$PERCEPTION_DETECTIONS_PATH" ]; then
    echo "Detection fixture: $PERCEPTION_DETECTIONS_PATH"
fi
if [ -n "$DETECTOR_BACKEND" ]; then
    echo "Detector backend: $DETECTOR_BACKEND"
fi
if [ -n "$DETECTOR_URL" ]; then
    echo "Detector URL: $DETECTOR_URL"
fi
cd "$PROJECT_DIR"
uv run python -m capabilities.server --host "$CAPABILITY_SERVER_HOST" --port "$CAPABILITY_SERVER_PORT" "${EXTRA_ARGS[@]}"
