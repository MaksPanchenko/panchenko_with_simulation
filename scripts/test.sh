#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/build.sh"
distro="$(<"$ROOT/.runtime/ros-distro")"
source "/opt/ros/$distro/setup.bash"
source install/setup.bash
export ROS_LOG_DIR="$ROOT/.runtime/test-ros-log"
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-73}"
mkdir -p "$ROS_LOG_DIR"
colcon test --base-paths . --packages-select multiwii --event-handlers console_direct+
colcon test-result --verbose
python3 test/integration.py
