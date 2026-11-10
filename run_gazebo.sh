#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$ROOT/scripts/build.sh"
"$ROOT/scripts/build_gazebo.sh"
distro="$(<"$ROOT/.runtime/ros-distro")"
source "/opt/ros/$distro/setup.bash"
source "$ROOT/install/setup.bash"
exec python3 "$ROOT/scripts/gazebo_session.py" "$@"
