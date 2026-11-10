#!/usr/bin/env bash
set -eo pipefail
mkdir -p /results
collect() {
    result=$?
    trap - EXIT
    for directory in .runtime log build/multiwii/test_results; do
        [[ ! -d "$directory" ]] || cp -R "$directory" /results/
    done
    printf '%s\n' "$result" > /results/exit-code
    exit "$result"
}
trap collect EXIT
source /etc/os-release
[[ "$VERSION_ID" == 24.04 ]]
source /opt/ros/jazzy/setup.bash
export ROS_LOCALHOST_ONLY=1
export CMAKE_BUILD_PARALLEL_LEVEL=2
export PYTHONUNBUFFERED=1
cat /etc/os-release > /results/os-release
dpkg --print-architecture > /results/architecture
dpkg-query -W ros-jazzy-rclcpp ros-jazzy-mavros-msgs libasio-dev > /results/packages
ROS_DOMAIN_ID=74 ./scripts/test.sh
source install/local_setup.bash
ROS_DOMAIN_ID=75 python3 scripts/test-launch.py
printf 'PASS: Ubuntu 24.04 / ROS 2 Jazzy, MSP telemetry, controller state and launch\n'
