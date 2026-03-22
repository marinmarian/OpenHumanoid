# ============================================================
# FAST_LIO_LOCALIZATION_HUMANOID — ROS2 Humble build
# ============================================================
FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

# ---- 1. System dependencies --------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git wget unzip ca-certificates \
    libc++-dev libc++abi-dev libeigen3-dev \
    libpcl-dev pcl-tools \
    python3-colcon-common-extensions python3-pip python3-rosdep \
    ros-humble-pcl-ros ros-humble-pcl-conversions \
    ros-humble-tf2-ros ros-humble-tf2-eigen \
    ros-humble-tf2-geometry-msgs ros-humble-tf2-sensor-msgs \
    ros-humble-eigen3-cmake-module \
    ros-humble-cv-bridge ros-humble-image-transport \
    ros-humble-rviz2 ros-humble-urdf \
    ros-humble-navigation2 ros-humble-nav2-bringup \
    ros-humble-nav2-mppi-controller \
    ros-humble-nav2-smac-planner \
    ros-humble-spatio-temporal-voxel-layer \
    ros-humble-pointcloud-to-laserscan \
    libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
    libglu1-mesa-dev libglfw3-dev libglew-dev \
    liblapacke-dev libopenblas-dev \
    libboost-filesystem-dev libboost-system-dev \
    libyaml-cpp-dev libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

# ---- 2. Livox-SDK2 (for livox_ros_driver2) -----------------
RUN cd /tmp && \
    git clone https://github.com/Livox-SDK/Livox-SDK2.git && \
    cd Livox-SDK2 && mkdir build && cd build && \
    cmake .. && make -j$(nproc) && make install && \
    ldconfig && \
    rm -rf /tmp/Livox-SDK2

# ---- 3. Open3D 0.14.1 — build from source ------------------
RUN pip3 install cmake==3.27.9 && \
    hash -r && cmake --version

RUN cd /opt && \
    git clone --depth 1 --branch v0.14.1 https://github.com/isl-org/Open3D.git open3d_src && \
    cd open3d_src && mkdir build && cd build && \
    cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/open3d141 \
      -DBUILD_SHARED_LIBS=ON \
      -DBUILD_PYTHON_MODULE=OFF \
      -DBUILD_EXAMPLES=OFF \
      -DBUILD_UNIT_TESTS=OFF \
      -DBUILD_BENCHMARKS=OFF \
      -DBUILD_GUI=OFF \
      -DUSE_SYSTEM_EIGEN3=OFF \
      -DGLIBCXX_USE_CXX11_ABI=ON \
    && make -j$(nproc) && make install && \
    rm -rf /opt/open3d_src

# ---- 4. livox_ros_driver2 (ROS2 Humble) --------------------
RUN mkdir -p /root/ws_livox/src && \
    cd /root/ws_livox/src && \
    git clone https://github.com/Livox-SDK/livox_ros_driver2.git && \
    cd livox_ros_driver2 && \
    cp package_ROS2.xml package.xml && \
    cd /root/ws_livox && \
    source /opt/ros/humble/setup.bash && \
    colcon build --cmake-args -DROS_EDITION=ROS2 -DHUMBLE_ROS=humble

# ---- 5. Copy project source into the image -----------------
RUN mkdir -p /root/ws_loc/src
COPY . /root/ws_loc/src/FAST_LIO_LOCALIZATION_HUMANOID
COPY bind_any.c /bind_any.c

# ---- 6. Fix Open3D path -------------------------------------
RUN sed -i 's|set(Open3D_DIR.*)|set(Open3D_DIR "/opt/open3d141/lib/cmake/Open3D")|' \
    /root/ws_loc/src/FAST_LIO_LOCALIZATION_HUMANOID/open3d_loc/CMakeLists.txt

# ---- 7. Build the full workspace ---------------------------
RUN cd /root/ws_loc && \
    source /opt/ros/humble/setup.bash && \
    source /root/ws_livox/install/setup.bash && \
    colcon build --symlink-install

# ---- 9. Entrypoint -----------------------------------------
# Build LD_PRELOAD shim so livox SDK can bind to 0.0.0.0 inside Docker
# while advertising the real host IP to the LiDAR
RUN gcc -shared -fPIC -o /usr/lib/bind_any.so /bind_any.c -ldl

RUN printf '#!/bin/bash\nsource /opt/ros/humble/setup.bash\nsource /root/ws_livox/install/setup.bash\nsource /root/ws_loc/install/setup.bash\nexec "$@"\n' > /ros_entrypoint.sh && chmod +x /ros_entrypoint.sh

# Source ROS2 in every interactive shell
RUN echo 'source /opt/ros/humble/setup.bash' >> /root/.bashrc && \
    echo 'source /root/ws_livox/install/setup.bash' >> /root/.bashrc && \
    echo 'source /root/ws_loc/install/setup.bash' >> /root/.bashrc

# ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["bash"]
