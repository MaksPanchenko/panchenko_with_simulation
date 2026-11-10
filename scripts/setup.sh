#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.runtime"
mkdir -p "$STATE"
mode="${1:-ros}"
as_root() { if (( EUID == 0 )); then "$@"; else sudo -- "$@"; fi; }
source /etc/os-release
[[ "$ID" == ubuntu && ( "$VERSION_ID" == 22.04 || "$VERSION_ID" == 24.04 ) ]] || {
    echo 'Нужна Ubuntu 22.04 или 24.04.' >&2; exit 1;
}
architecture="$(dpkg --print-architecture)"
[[ "$architecture" == amd64 || "$architecture" == arm64 ]]
if [[ "$VERSION_ID" == 22.04 ]]; then distro=humble; else distro=jazzy; fi
ros_packages=(build-essential cmake libasio-dev libeigen3-dev python3-colcon-common-extensions
    "ros-$distro-ros-base" "ros-$distro-mavros-msgs" "ros-$distro-tf2-ros" "ros-$distro-ament-cmake-gtest")
case "$mode" in
    ros) packages=("${ros_packages[@]}") ;;
    gazebo) packages=("${ros_packages[@]}" gz-harmonic libgz-sim8-dev libgz-plugin2-dev
        libgz-math7-dev libgz-transport13-dev) ;;
    qemu) packages=(qemu-system-arm qemu-utils qemu-efi-aarch64 cloud-image-utils curl openssh-client python3) ;;
    docker)
        if command -v docker >/dev/null; then exit 0; fi
        packages=(docker.io) ;;
    *) echo 'Используйте: setup.sh ros|gazebo|qemu|docker' >&2; exit 1 ;;
esac
if [[ "$mode" == ros || "$mode" == gazebo ]]; then
    [[ -z "${ROS_DISTRO:-}" || "$ROS_DISTRO" == "$distro" ]] || {
        echo "Откройте терминал без окружения $ROS_DISTRO: для Ubuntu $VERSION_ID используется $distro." >&2
        exit 1
    }
    printf '%s\n' "$distro" > "$STATE/ros-distro"
fi
signature="$(printf '%s\n' "$ROOT" "$VERSION_ID" "$architecture" "${packages[@]}" \
    "$(sha256sum "$ROOT/scripts/setup.sh")" | sha256sum | cut -d' ' -f1)"
marker="$STATE/setup-$mode.state"
[[ ! -f "$marker" || "$(<"$marker")" != "$signature" ]] || exit 0
missing=()
for package in "${packages[@]}"; do
    [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" == 'install ok installed' ]] || missing+=("$package")
done
if (( ${#missing[@]} )); then
    as_root apt-get update
    if [[ "$mode" == ros || "$mode" == gazebo ]] && ! apt-cache show "ros-$distro-ros-base" >/dev/null 2>&1; then
        as_root apt-get install -y --no-remove --no-install-recommends ca-certificates curl software-properties-common
        as_root add-apt-repository -y -n universe
        if [[ "$VERSION_ID" == 24.04 && -f /etc/apt/sources.list.d/ubuntu.sources ]]; then
            as_root python3 - /etc/apt/sources.list.d/ubuntu.sources <<'PY'
from pathlib import Path
import re
import shutil
import sys

path = Path(sys.argv[1])
original = path.read_text()
def enable_pockets(match):
    fields = match.group().split()
    if 'noble' not in fields:
        return match.group()
    missing = [p for p in ('noble-updates', 'noble-backports') if p not in fields]
    return match.group() + ''.join(' ' + p for p in missing)
updated = re.sub(r'^Suites:[^\n]*', enable_pockets, original, flags=re.MULTILINE | re.IGNORECASE)
if updated != original:
    backup = path.with_suffix('.sources.bak')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(updated)
PY
        fi
        curl -fL --retry 3 -o "$STATE/ros2-apt-source.deb" \
            "https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.2.0/ros2-apt-source_1.2.0.${VERSION_CODENAME}_all.deb"
        as_root apt-get install -y --no-remove "$STATE/ros2-apt-source.deb"
        as_root apt-get update
    fi
    if [[ "$mode" == gazebo ]] && ! apt-cache show gz-harmonic >/dev/null 2>&1; then
        as_root apt-get install -y --no-remove --no-install-recommends ca-certificates curl
        curl -fL --retry 3 https://packages.osrfoundation.org/gazebo.gpg -o "$STATE/gazebo.gpg"
        as_root install -m 644 "$STATE/gazebo.gpg" /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
        printf 'deb [arch=%s signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable %s main\n' \
            "$architecture" "$VERSION_CODENAME" | as_root tee /etc/apt/sources.list.d/gazebo-stable.list >/dev/null
        as_root apt-get update
    fi
    as_root apt-get install -y --no-remove --no-install-recommends "${missing[@]}"
fi
printf '%s\n' "$signature" > "$marker.tmp"
mv "$marker.tmp" "$marker"
