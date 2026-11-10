#!/usr/bin/env bash
# Run INSIDE the Ubuntu 22.04 ARM64 guest. The same dependencies work on amd64.
set -euo pipefail
source /etc/os-release
[[ "$VERSION_CODENAME" == jammy ]] || { echo "Requires Ubuntu 22.04 (jammy)" >&2; exit 1; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/setup.sh" ros
