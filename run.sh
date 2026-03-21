#!/bin/bash
# ============================================================
# run.sh — Build & run the localization Docker container
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Create bags dir if it doesn't exist
mkdir -p bags

echo "=== Building Docker image (this will take a while the first time) ==="
docker compose build

echo ""
echo "=== Starting container ==="
echo "Inside the container, run:"
echo ""
echo "  # Launch localization (FAST_LIO + Open3D + rviz):"
echo "  roslaunch open3d_loc localization_3d_g1.launch"
echo ""
echo "  # In another terminal (docker exec -it fast_lio_loc bash):"
echo "  # Option A — play a rosbag:"
echo "  rosbag play /root/bags/loc.bag"
echo ""
echo "  # Option B — live LiDAR:"
echo "  roslaunch livox_ros_driver2 msg_MID360.launch"
echo ""
echo "  # Then in rviz: click '2D Pose Estimate' and set initial pose"
echo ""

docker compose up -d
docker compose exec localization bash
