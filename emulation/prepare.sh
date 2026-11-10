#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VM="$ROOT/.runtime/qemu"
mkdir -p "$VM"
if [[ -e "$VM/disk.qcow2" ]]; then
    echo "VM already prepared: $VM (remove it explicitly to start over)"
    exit 0
fi
for tool in qemu-img cloud-localds ssh-keygen; do command -v "$tool" >/dev/null; done
if [[ "${1:-}" == --reuse && $# == 2 ]]; then
    qemu-img convert -O qcow2 "$2" "$VM/disk.qcow2.partial"
elif [[ "${1:-}" == --image && $# == 2 ]]; then
    qemu-img convert -O qcow2 "$2" "$VM/disk.qcow2.partial"
    qemu-img resize "$VM/disk.qcow2.partial" 20G
elif [[ $# == 0 ]]; then
    base=https://cloud-images.ubuntu.com/jammy/current
    curl -fL "$base/jammy-server-cloudimg-arm64.img" -o "$VM/base.img"
    curl -fL "$base/SHA256SUMS" -o "$VM/SHA256SUMS"
    python3 - "$VM" <<'PY'
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
expected = next(line.split()[0] for line in (root / 'SHA256SUMS').read_text().splitlines()
                if line.split()[-1].lstrip('*') == 'jammy-server-cloudimg-arm64.img')
with (root / 'base.img').open('rb') as stream:
    actual = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else None
if actual is None:
    digest = hashlib.sha256()
    with (root / 'base.img').open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest.update(chunk)
    actual = digest.hexdigest()
if actual != expected: raise SystemExit('Ubuntu image SHA256 mismatch')
PY
    qemu-img convert -O qcow2 "$VM/base.img" "$VM/disk.qcow2.partial"
    qemu-img resize "$VM/disk.qcow2.partial" 20G
else
    echo "Usage: $0 [--image cloud-image | --reuse existing-guest-disk]" >&2
    exit 2
fi
[[ -f "$VM/id_ed25519" ]] || ssh-keygen -q -t ed25519 -N '' -f "$VM/id_ed25519"
VM_KEY="$(cat "$VM/id_ed25519.pub")"
cat > "$VM/user-data" <<EOF
#cloud-config
users:
  - name: reviewer
    groups: [sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: true
    ssh_authorized_keys:
      - $VM_KEY
ssh_pwauth: false
disable_root: true
package_update: false
EOF
printf 'instance-id: multiwii-%s\nlocal-hostname: multiwii-arm64\n' "$(date +%s)" > "$VM/meta-data"
cloud-localds "$VM/seed.img" "$VM/user-data" "$VM/meta-data"
cp /usr/share/AAVMF/AAVMF_VARS.fd "$VM/vars.fd"
mv "$VM/disk.qcow2.partial" "$VM/disk.qcow2"
echo "Prepared $VM. Start with emulation/start.sh."
