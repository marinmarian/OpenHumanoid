cmake_minimum_required(VERSION 3.8)
project(nav2_humanoid)

find_package(ament_cmake REQUIRED)

# Install config files
install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

# Install launch files
install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

# Install executable scripts
install(PROGRAMS scripts/object_goal_sender
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
