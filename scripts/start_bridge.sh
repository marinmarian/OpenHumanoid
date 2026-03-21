#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WBC_CONTAINER="${WBC_CONTAINER:-decoupled_wbc-bash-root}"
BRIDGE_PORT="${BRIDGE_PORT:-8765}"
ROBOT_NIC="${ROBOT_NIC:-enp0s31f6}"
INTERFACE="${1:-sim}"

if ! docker ps --format '{{.Names}}' | grep -q "^${WBC_CONTAINER}$"; then
    echo "Container '$WBC_CONTAINER' is not running."
    echo "Start it first:  cd GR00T-WholeBodyControl/decoupled_wbc && ./docker/run_docker.sh --root"
    exit 1
fi

docker exec "$WBC_CONTAINER" pkill -9 -f run_with_bridge.py 2>/dev/null || true
sleep 1

echo "Copying bridge to container..."
docker cp "$PROJECT_DIR/bridge/run_with_bridge.py" "$WBC_CONTAINER:/tmp/run_with_bridge.py"

LOOP_ARGS=""
if [ "$INTERFACE" = "real" ]; then
    LOOP_ARGS="-- --interface real --no-with_hands"
    echo "Starting bridge + control loop (real robot, hands disabled)..."
else
    echo "Starting bridge + control loop (simulation)..."
fi

docker exec "$WBC_CONTAINER" bash -c \
    "source /opt/ros/humble/setup.bash && source /root/venv/bin/activate && python3 /tmp/run_with_bridge.py --port $BRIDGE_PORT $LOOP_ARGS"
