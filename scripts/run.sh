#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/scripts/build.sh"
distro="$(<"$ROOT/.runtime/ros-distro")"
source "/opt/ros/$distro/setup.bash"
source "$ROOT/install/setup.bash"
export ROS_LOG_DIR="$ROOT/.runtime/ros-log"
mkdir -p "$ROS_LOG_DIR"
exec ros2 launch multiwii system.launch.py "$@"
