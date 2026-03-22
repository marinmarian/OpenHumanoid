#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

DETECTOR_SERVER_HOST="${DETECTOR_SERVER_HOST:-127.0.0.1}"
DETECTOR_SERVER_PORT="${DETECTOR_SERVER_PORT:-8790}"
DETECTOR_SERVICE_BACKEND="${DETECTOR_SERVICE_BACKEND:-ultralytics}"
DETECTOR_MODEL="${DETECTOR_MODEL:-}"
DETECTOR_FIXTURE_PATH="${DETECTOR_FIXTURE_PATH:-}"
DETECTOR_TIMEOUT_S="${DETECTOR_TIMEOUT_S:-}"

if [ -z "$DETECTOR_MODEL" ]; then
    if [ "$DETECTOR_SERVICE_BACKEND" = "openai" ]; then
        DETECTOR_MODEL="gpt-4.1-mini"
    elif [ "$DETECTOR_SERVICE_BACKEND" = "ultralytics" ]; then
        DETECTOR_MODEL="yolov8n.pt"
    fi
fi

EXTRA_ARGS=(--host "$DETECTOR_SERVER_HOST" --port "$DETECTOR_SERVER_PORT" --backend "$DETECTOR_SERVICE_BACKEND")
if [ -n "$DETECTOR_MODEL" ]; then
    EXTRA_ARGS+=(--model "$DETECTOR_MODEL")
fi
if [ -n "$DETECTOR_FIXTURE_PATH" ]; then
    EXTRA_ARGS+=(--fixture-path "$DETECTOR_FIXTURE_PATH")
fi
if [ -n "$DETECTOR_TIMEOUT_S" ]; then
    EXTRA_ARGS+=(--timeout-s "$DETECTOR_TIMEOUT_S")
fi

echo "Starting detector service on http://${DETECTOR_SERVER_HOST}:${DETECTOR_SERVER_PORT}"
echo "Detector backend: ${DETECTOR_SERVICE_BACKEND}"
if [ -n "$DETECTOR_MODEL" ]; then
    echo "Detector model: ${DETECTOR_MODEL}"
fi
if [ -n "$DETECTOR_FIXTURE_PATH" ]; then
    echo "Detector fixture: ${DETECTOR_FIXTURE_PATH}"
fi
if [ "$DETECTOR_SERVICE_BACKEND" = "openai" ]; then
    echo "OpenAI VLM backend enabled"
fi

cd "$PROJECT_DIR"
uv run python scripts/detector_service.py "${EXTRA_ARGS[@]}"
