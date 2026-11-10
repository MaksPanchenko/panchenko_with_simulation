#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$ROOT/scripts/setup.sh" qemu
exec python3 "$ROOT/scripts/raspberry_session.py" "$@"
