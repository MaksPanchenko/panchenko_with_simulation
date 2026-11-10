#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec ssh -i "$ROOT/.runtime/qemu/id_ed25519" -p "${VM_SSH_PORT:-2233}" \
  -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
  -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=12 \
  -o "UserKnownHostsFile=$ROOT/.runtime/qemu/known_hosts" \
  -o ConnectTimeout=5 reviewer@127.0.0.1 "$@"
