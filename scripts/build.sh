#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/setup.sh" ros
distro="$(<"$ROOT/.runtime/ros-distro")"
source "/opt/ros/$distro/setup.bash"
if [[ -f build/multiwii/CMakeCache.txt ]] &&
   { ! grep -Fqx "CMAKE_HOME_DIRECTORY:INTERNAL=$ROOT" build/multiwii/CMakeCache.txt ||
     ! grep -Fq "rclcpp_DIR:PATH=/opt/ros/$distro/" build/multiwii/CMakeCache.txt; }; then
    rm -rf -- "$ROOT/build" "$ROOT/install"
fi
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
export CC=/usr/bin/gcc
export CXX=/usr/bin/g++
colcon build --base-paths . --executor sequential --event-handlers desktop_notification- \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON "$@"
