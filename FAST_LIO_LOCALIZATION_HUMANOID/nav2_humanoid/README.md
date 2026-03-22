# Nav2 Navigation for Unitree G1 Humanoid

Nav2 integration layered on top of the FAST-LIO + Open3D localization stack.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Livox MID360  →  FAST-LIO (odometry)                   │
│                       ↓                                  │
│               Open3D Localization (map→odom TF)          │
│                       ↓                                  │
│  ┌─────────────── Nav2 Stack ──────────────────────┐    │
│  │  bt_navigator                                    │    │
│  │  planner_server  (NavfnPlanner)                  │    │
│  │  controller_server (DWB – omnidirectional)       │    │
│  │  behavior_server  (spin, backup, wait)           │    │
│  │  smoother_server                                 │    │
│  │  velocity_smoother → /cmd_vel                    │    │
│  │  costmap_2d (local: VoxelLayer, global: Obstacle)│    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**TF chain** (provided by localization):
```
map → odom → camera_init → imu_link → base_link → motion_link
```

**Key topics**:
| Topic | Type | Source |
|-------|------|--------|
| `/cloud_registered_body_1` | PointCloud2 | FAST-LIO (obstacle detection) |
| `/Odometry_loc` | Odometry | FAST-LIO (odom) |
| `/cmd_vel` | Twist | Nav2 → G1 locomotion |
| `/goal_pose` | PoseStamped | RViz "Nav2 Goal" button |

## Quick Start

### Option A — Full stack (localization + Nav2)

```bash
# Build & run Docker container
./run.sh

# Inside container — start everything:
ros2 launch nav2_humanoid full_navigation_g1.launch.py

# In another terminal, start the lidar driver:
docker exec -it fast_lio_loc bash
ros2 launch livox_ros_driver2 msg_MID360_launch.py

# Set initial pose in RViz (2D Pose Estimate tool)
# Then send goals with "Nav2 Goal" tool
```

### Option B — Nav2 only (localization already running)

```bash
# Terminal 1: localization (already running)
ros2 launch open3d_loc localization_3d_g1.launch.py

# Terminal 2: Nav2 navigation
ros2 launch nav2_humanoid nav2_g1.launch.py
```

### Sending goals programmatically

```bash
# Send a navigation goal
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: 'map'}, pose: {position: {x: 5.0, y: 2.0, z: 0.0}, orientation: {w: 1.0}}}}"

# Cancel current goal
ros2 action cancel_goal /navigate_to_pose
```

## Configuration

Edit `config/nav2_params_g1.yaml` to tune:

| Parameter | Default | Notes |
|-----------|---------|-------|
| `max_vel_x` | 0.5 m/s | Forward walking speed |
| `max_vel_y` | 0.3 m/s | Lateral strafe speed |
| `max_vel_theta` | 1.0 rad/s | Rotation speed |
| `robot_radius` | 0.25 m | Footprint for costmap |
| `inflation_radius` | 0.55 m | Safety buffer around obstacles |
| Local costmap size | 6×6 m | Rolling window around robot |
| Global costmap size | 50×50 m | Rolling window in map frame |

### Using a static 2D map

If you have a 2D occupancy grid (from the 3D PCD or otherwise):

1. Uncomment the `static_layer` in the global costmap section of `nav2_params_g1.yaml`
2. Launch the map server:
```bash
ros2 run nav2_map_server map_server --ros-args -p yaml_filename:=/path/to/map.yaml
ros2 run nav2_util lifecycle_bringup map_server
```

### Optional: pointcloud to 2D scan

```bash
ros2 launch nav2_humanoid full_navigation_g1.launch.py enable_pointcloud_to_laserscan:=true
```
This publishes `/scan` (LaserScan) converted from the 3D lidar, useful for debugging.

## Files

```
nav2_humanoid/
├── CMakeLists.txt
├── package.xml
├── config/
│   ├── nav2_params_g1.yaml          # All Nav2 parameters
│   └── nav2_default_view.rviz       # RViz config with Nav2 displays
└── launch/
    ├── nav2_g1.launch.py            # Nav2 only (localization separate)
    └── full_navigation_g1.launch.py # Everything: FAST-LIO + Open3D + Nav2
```
