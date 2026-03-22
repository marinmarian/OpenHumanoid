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