#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$ROOT/scripts/setup.sh" docker
STATE="$ROOT/.runtime/docker"
mkdir -p "$STATE/results"
context="${TEST_DOCKER_CONTEXT:-$(docker context show)}"
docker_command=(docker --context "$context")
if ! "${docker_command[@]}" info >/dev/null 2>&1; then
    if [[ "$context" != default ]]; then
        echo "Запустите Docker для контекста $context." >&2
        exit 1
    fi
    if (( EUID == 0 )); then root_command=(); else root_command=(sudo); fi
    if command -v systemctl >/dev/null; then "${root_command[@]}" systemctl start docker; fi
    docker_command=("${root_command[@]}" docker --context default)
    "${docker_command[@]}" info >/dev/null
fi
image=multiwii-simulation-jazzy:local
"${docker_command[@]}" build -f "$ROOT/docker/Dockerfile" -t "$image" "$ROOT" 2>&1 | tee "$STATE/build.log"
"${docker_command[@]}" run --rm --init --network none --shm-size=256m \
    --mount "type=bind,src=$STATE/results,dst=/results" "$image" 2>&1 | tee "$STATE/checks.log"
