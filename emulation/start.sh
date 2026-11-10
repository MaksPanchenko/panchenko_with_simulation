#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VM="$ROOT/.runtime/qemu"
[[ -f "$VM/disk.qcow2" ]] || { echo "Run emulation/prepare.sh first" >&2; exit 1; }
# QEMU's own exclusive disk lock prevents two instances from sharing the disk.
exec qemu-system-aarch64 \
  -name multiwii-arm64 -machine virt -accel tcg,thread=multi -cpu cortex-a72 \
  -smp "${VM_CPUS:-2}" -m "${VM_MEMORY:-3072}" \
  -drive if=pflash,format=raw,unit=0,file=/usr/share/AAVMF/AAVMF_CODE.fd,readonly=on \
  -drive "if=pflash,format=raw,unit=1,file=$VM/vars.fd" \
  -drive "if=virtio,format=qcow2,file=$VM/disk.qcow2" \
  -drive "if=virtio,format=raw,file=$VM/seed.img,readonly=on" \
  -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:${VM_SSH_PORT:-2233}-:22" \
  -device virtio-net-pci,netdev=net0 -nographic
