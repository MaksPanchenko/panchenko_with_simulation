#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tar -C "$ROOT" --exclude='./.runtime' --exclude='./build' --exclude='./install' \
  --exclude='./simulation' \
  --exclude='./log' --exclude='./.git' \
  --exclude='__pycache__' -czf - . | \
  "$ROOT/emulation/ssh.sh" 'mkdir -p ~/temporary && tar -xzf - -C ~/temporary'
