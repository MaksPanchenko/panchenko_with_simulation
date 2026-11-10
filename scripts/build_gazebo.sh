#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.runtime/gazebo"
SOURCE="$STATE/betaflight-source"
mkdir -p "$STATE/bin"
"$ROOT/scripts/setup.sh" gazebo
distro="$(<"$ROOT/.runtime/ros-distro")"
source "/opt/ros/$distro/setup.bash"
if [[ -f "$STATE/plugin-build/CMakeCache.txt" ]] &&
   ! grep -Fqx "CMAKE_HOME_DIRECTORY:INTERNAL=$ROOT/simulation" "$STATE/plugin-build/CMakeCache.txt"; then
    rm -rf -- "$STATE/plugin-build"
fi
cmake -S "$ROOT/simulation" -B "$STATE/plugin-build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
  -DCMAKE_INSTALL_PREFIX="$STATE"
cmake --build "$STATE/plugin-build" --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
cmake --install "$STATE/plugin-build"
if [[ ! -f "$SOURCE/Makefile" ]]; then
    mkdir -p "$SOURCE"
    tar -xzf "$ROOT/simulation/vendor/betaflight-sitl.tar.gz" -C "$SOURCE"
fi
PATH="/usr/bin:/bin:$PATH" make -C "$SOURCE" TARGET=SITL AUTOHYDRATE_SUBMODULES= CCACHE= \
  REVISION=a12049c58 -j"${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
cp "$SOURCE/obj/main/betaflight_SITL.elf" "$STATE/bin/betaflight_SITL.elf"
printf '\nGazebo/SITL собраны. Запуск: ./run_gazebo.sh\n'
