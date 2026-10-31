FROM ros:humble-ros-base-jammy

SHELL ["/bin/bash", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates gnupg python3-colcon-common-extensions \
    python3-rosdep python3-yaml libgl1-mesa-dri libegl1-mesa mesa-utils \
    ros-humble-rmw-cyclonedds-cpp \
    && curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
       -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main" \
       > /etc/apt/sources.list.d/gazebo-stable.list

# .dockerignore admits only package manifests from the authenticated host checkout.
# No GitHub credentials, foundation code, or private meshes enter the image.
COPY external/lifth_arm_gen2/src/ /tmp/foundation/src/
RUN test -f /etc/ros/rosdep/sources.list.d/20-default.list || rosdep init
RUN rosdep update --rosdistro humble \
    && apt-get update \
    && rosdep install --from-paths /tmp/foundation/src --ignore-src --rosdistro humble -y \
    && rm -rf /tmp/foundation /var/lib/apt/lists/*

ENV LIBGL_ALWAYS_SOFTWARE=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=204 IGN_PARTITION=pai_issue1 \
    HOME=/tmp ROS_LOG_DIR=/pai/outputs/ros
WORKDIR /pai
CMD ["sleep", "infinity"]
