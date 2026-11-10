FROM ros:jazzy-ros-base-noble@sha256:8eed0a4669bbf43ee331878a4c39bd8ebddea8e3312a58b4fae8edb14526b617
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasio-dev libeigen3-dev ros-jazzy-mavros-msgs \
    ros-jazzy-tf2-ros ros-jazzy-ament-cmake-gtest \
    && rm -rf /var/lib/apt/lists/*
COPY . /work/multiwii/
WORKDIR /work/multiwii
ENTRYPOINT ["/bin/bash", "/work/multiwii/docker/run_checks.sh"]
