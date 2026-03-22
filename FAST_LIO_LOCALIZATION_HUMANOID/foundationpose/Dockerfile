# ============================================================
# FoundationPoseROS2 — NVIDIA CUDA + ROS2 Humble
# Requires: NVIDIA GPU (≥8 GB VRAM), nvidia-container-toolkit
#
# BUILD ON A LINUX x86_64 MACHINE WITH AN NVIDIA GPU.
# This cannot build or run on macOS (no NVIDIA GPU support).
# ============================================================
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

# ---- 1. ROS2 Humble ----------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common curl gnupg lsb-release wget git \
        build-essential cmake \
    && add-apt-repository universe \
    && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
        http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/ros2.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-ros-base \
        ros-humble-cv-bridge \
        ros-humble-sensor-msgs \
        ros-humble-geometry-msgs \
        ros-humble-tf2-ros \
        ros-humble-tf2-geometry-msgs \
        ros-humble-image-transport \
        ros-humble-realsense2-camera \
        python3-colcon-common-extensions \
        python3-pip python3-dev python3-tk \
    && rm -rf /var/lib/apt/lists/*

# ---- 2. FoundationPoseROS2 source --------------------------
WORKDIR /app
RUN git clone https://github.com/ammar-n-abbas/FoundationPoseROS2.git /app/FoundationPoseROS2

# ---- 3. Python deps (system Python 3.10, no conda) ---------
RUN pip3 install --no-cache-dir \
        torchvision==0.16.0+cu121 torchaudio==2.1.0 torch==2.1.0+cu121 \
        --index-url https://download.pytorch.org/whl/cu121 \
    && pip3 install --no-cache-dir \
        "git+https://github.com/facebookresearch/pytorch3d.git@stable" \
    && cd /app/FoundationPoseROS2 \
    && pip3 install --no-cache-dir -r requirements.txt

# ---- 4. FoundationPose core + extensions --------------------
RUN cd /app/FoundationPoseROS2 \
    && git clone https://github.com/NVlabs/FoundationPose.git \
    && cd FoundationPose \
    # Update C++ standard for newer GPUs
    && sed -i 's/c++14/c++17/g' bundlesdf/mycuda/setup.py \
    # pybind11
    && git clone https://github.com/pybind/pybind11 && cd pybind11 \
    && git checkout v2.10.0 && mkdir build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release -DPYBIND11_INSTALL=ON -DPYBIND11_TEST=OFF \
    && make -j$(nproc) && make install \
    && cd /app/FoundationPoseROS2/FoundationPose \
    # Eigen
    && wget -q https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz \
    && tar xzf eigen-3.4.0.tar.gz && rm eigen-3.4.0.tar.gz \
    && cd eigen-3.4.0 && mkdir build && cd build && cmake .. && make install \
    && cd /app/FoundationPoseROS2/FoundationPose \
    # nvdiffrast
    && git clone https://github.com/NVlabs/nvdiffrast && cd nvdiffrast && pip3 install . \
    && cd /app/FoundationPoseROS2/FoundationPose \
    # mycpp
    && cd mycpp && rm -rf build && mkdir -p build && cd build && cmake .. && make -j$(nproc) \
    && cd /app/FoundationPoseROS2/FoundationPose \
    # mycuda
    && cd bundlesdf/mycuda && rm -rf build *egg* *.so && pip3 install -e .

# ---- 5. Download pretrained weights ------------------------
RUN pip3 install --no-cache-dir gdown \
    && mkdir -p /app/FoundationPoseROS2/FoundationPose/weights \
    && gdown --folder https://drive.google.com/drive/folders/1BEQLZH69UO5EOfah-K9bfI3JyP9Hf7wC \
        -O /app/FoundationPoseROS2/FoundationPose/weights/2023-10-28-18-33-37 \
    && gdown --folder https://drive.google.com/drive/folders/12Te_3TELLes5cim1d7F7EBTwUSe7iRBj \
        -O /app/FoundationPoseROS2/FoundationPose/weights/2024-01-11-20-02-45

# ---- 6. Copy integration scripts ---------------------------
COPY object_goal_sender.py /app/object_goal_sender.py

# ---- 7. Entrypoint -----------------------------------------
RUN printf '#!/bin/bash\nsource /opt/ros/humble/setup.bash\nexec "$@"\n' \
    > /ros_entrypoint.sh && chmod +x /ros_entrypoint.sh

RUN echo 'source /opt/ros/humble/setup.bash' >> /root/.bashrc

ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["bash"]

