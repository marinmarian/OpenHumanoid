#Build 
docker compose build && docker compose up -d       

# Run
docker compose up -d
docker exec -it fast_lio_loc /ros_entrypoint.sh bash

## Inside container — launch localization
ros2 launch open3d_loc localization_3d_g1.launch.py

# In another terminal — launch LiDAR driver

## Run 
- docker exec -it fast_lio_loc /ros_entrypoint.sh bash

## Inside container run

- LD_PRELOAD=/usr/lib/bind_any.so ros2 launch livox_ros_driver2 msg_MID360_launch.py

# To run the whole setup (mapping + localization + navigation) - also run lidar driver 
- docker exec -it fast_lio_loc bash
- ros2 launch nav2_humanoid full_navigation_g1.launch.py



# Full pipeline (FAST-LIO + localization + Nav2 + object detection + goal sender)

## Build (on Linux x86_64 with NVIDIA GPU)
```bash
cd FAST_LIO_LOCALIZATION_HUMANOID
docker compose --profile gpu build
docker compose --profile gpu up -d
```

or just 
```bash
docker compose build 
```

## Terminal 1 — Nav stack + localization + goal sender
```bash
docker exec -it fast_lio_loc bash
ros2 launch nav2_humanoid detection_navigation_g1.launch.py
```

## Terminal 2 — LiDAR driver
```bash
docker exec -it fast_lio_loc bash
LD_PRELOAD=/usr/lib/bind_any.so ros2 launch livox_ros_driver2 msg_MID360_launch.py
```

## Terminal 3 — Object detection (GPU container)
```bash
docker exec -it foundation_pose bash
cd /app/FoundationPoseROS2
python3 foundationpose_ros_multi.py
```

## Then in RViz
1. Click **2D Pose Estimate** to set the robot's initial position on the map
2. Wait for localization to converge
3. FoundationPose detects objects → goal sender navigates the robot to them automatically