#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

VOICE_MODE="${VOICE_MODE:-realtime}"
BRIDGE_URL="${BRIDGE_URL:-http://localhost:8765}"

echo "=== OpenHumanoid Launch ==="
echo "Mode: $VOICE_MODE"
echo "Bridge: $BRIDGE_URL"
echo ""

# Check bridge is reachable
echo "Checking bridge at $BRIDGE_URL/status ..."
if curl -sf "$BRIDGE_URL/status" > /dev/null 2>&1; then
    echo "Bridge is running."
else
    echo "WARNING: Bridge not reachable at $BRIDGE_URL"
    echo "Start it first:"
    echo "  Mock:   uv run python bridge/mock_bridge.py"
    echo '  Docker: docker exec <container> bash -c "source /opt/ros/humble/setup.bash && python3 /tmp/bridge_server.py"'
    echo ""
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""

case "$VOICE_MODE" in
    realtime)
        echo "Starting Realtime API voice client (fast mode)..."
        cd "$PROJECT_DIR"
        uv run python -m realtime.main
        ;;
    openclaw)
        echo "Starting OpenClaw Gateway (full mode)..."
        if ! command -v openclaw &>/dev/null; then
            echo "OpenClaw not installed. Run: cd openclaw && bash setup.sh"
            exit 1
        fi
        openclaw gateway start
        ;;
    *)
        echo "Unknown VOICE_MODE: $VOICE_MODE (use 'realtime' or 'openclaw')"
        exit 1
        ;;
esac
