# ============================================================
# FAST_LIO_LOCALIZATION_HUMANOID — ROS2 $ROS_DISTRO build
# ============================================================
FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
ENV RCUTILS_COLORIZED_OUTPUT=1
SHELL ["/bin/bash", "-c"]

RUN  apt-get update \
    && apt-get upgrade -y 

# Install required packages
RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    --mount=type=cache,sharing=locked,target=/root/.cache \
    apt-get update \
    && apt-get install -qqy --no-install-recommends \
        # general dependencies
        bash-completion \
        build-essential \
        clang \
        clang-format \
        cmake \
        gdb \
        git \
        htop \
        nano \
        iputils-ping \
        net-tools \
        sudo \
        wget \
        vim \
        unzip \
        python3-pip \
        python3-setuptools \
        python3-dev \
        ros-dev-tools

RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    --mount=type=cache,sharing=locked,target=/root/.cache \
    apt-get update \
    && apt-get install -qqy --no-install-recommends \
        ros-$ROS_DISTRO-navigation2 \
        ros-$ROS_DISTRO-nav2-bringup \
        ros-$ROS_DISTRO-nav2-mppi-controller \
        ros-$ROS_DISTRO-nav2-smac-planner \
        ros-$ROS_DISTRO-spatio-temporal-voxel-layer \
        ros-$ROS_DISTRO-pointcloud-to-laserscan


# ---- 2. Livox-SDK2 (for livox_ros_driver2) -----------------
RUN cd /tmp && \
git clone https://github.com/Livox-SDK/Livox-SDK2.git && \
    cd Livox-SDK2 && mkdir build && cd build && \
    cmake -S .. -B build && \
    cmake --build build  && \
    cmake --install build && \
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

# Create the user
RUN groupadd --gid 1000 g1_user \
    && useradd --uid 1000 --gid 1000 -m g1_user \
    && echo g1_user ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/g1_user \
    && chmod 0440 /etc/sudoers.d/g1_user

# Keep bash history when docker is rebuilt
RUN mkdir /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R g1_user /commandhistory \
    && echo "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" >> "/home/g1_user/.bashrc"

USER g1_user

# ---- 4. livox_ros_driver2 (ROS2 $ROS_DISTRO) --------------------
RUN mkdir -p /home/g1_user/ws_livox/src && \
    cd /home/g1_user/ws_livox/src && \
    git clone https://github.com/Livox-SDK/livox_ros_driver2.git && \
    cd livox_ros_driver2 && \
    cp package_ROS2.xml package.xml && \
    cd /home/g1_user/ws_livox && \
    source /opt/ros/$ROS_DISTRO/setup.bash && \
    colcon build --cmake-args -DROS_EDITION=ROS2 -DHUMBLE_ROS=humble

# ---- 5. Copy project source into the image -----------------
RUN mkdir -p /home/g1_user/ros2_ws/src
COPY . /home/g1_user/ros2_ws/src/FAST_LIO_LOCALIZATION_HUMANOID

# ---- 6. Fix Open3D path -------------------------------------
# RUN sed -i 's|set(Open3D_DIR.*)|set(Open3D_DIR "/opt/open3d141/lib/cmake/Open3D")|' \
    # /home/g1_user/ros2_ws/src/FAST_LIO_LOCALIZATION_HUMANOID/open3d_loc/CMakeLists.txt

# ---- 7. Build the full workspace ---------------------------
RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    --mount=type=cache,sharing=locked,target=/root/.cache \
    sudo apt-get update && \
    source /opt/ros/$ROS_DISTRO/setup.bash && \
    source /home/g1_user/ws_livox/install/setup.bash && \
    cd /home/g1_user/ros2_ws && \
    rosdep update --rosdistro $ROS_DISTRO && \
    rosdep install -y -i \
        --from-paths src \
        --rosdistro $ROS_DISTRO && \
    colcon build --symlink-install
        

WORKDIR /home/g1_user/ros2_ws

# Source ROS2 in every interactive shell
RUN echo 'source /opt/ros/$ROS_DISTRO/setup.bash' >> /home/g1_user/.bashrc && \
    echo 'source /home/g1_user/ws_livox/install/setup.bash' >> /home/g1_user/.bashrc && \
    echo 'source /home/g1_user/ros2_ws/install/setup.bash' >> /home/g1_user/.bashrc
