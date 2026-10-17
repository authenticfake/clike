#!/usr/bin/env bash
# Fast rebuild of the CLike stack that always runs the current code.
#
#   ./rebuild.sh                 # build gateway + orchestrator (eval-sandbox and eval-tools share its image)
#   ./rebuild.sh gateway         # build only the gateway
#   ./rebuild.sh orchestrator    # build only the orchestrator image
# The three services are always recreated (seconds): the orchestrator depends on the gateway,
# so recreating one alone fails with "has dependent containers".
#
# 1. frees the dangling layers of earlier builds (untagged, unused by any container);
# 2. builds with the layer cache: only the steps after a change run again
#    (source edits rebuild just `COPY . /app`; dependencies only when uv.lock changes);
# 3. recreates the containers: `up -d` alone keeps the old container when only the image changed;
# 4. waits until every container is (healthy) and checks it runs the image just built.
# Never use --no-cache: it does not help (the cache keys on file contents) and fills the VM disk.
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="$(basename "$PWD")"
TIMEOUT_S="${CLIKE_REBUILD_TIMEOUT_S:-180}"

case "${1:-all}" in
  all) build=(gateway orchestrator) ;;
  gateway) build=(gateway) ;;
  orchestrator | eval-sandbox) build=(orchestrator) ;;
  *) echo "usage: $0 [all|gateway|orchestrator]" >&2; exit 2 ;;
esac
run=(gateway orchestrator eval-sandbox eval-tools)

image_of() {
  case "$1" in
    gateway) echo "localhost/clike-gateway:latest" ;;
    *) echo "localhost/clike-orchestrator:latest" ;;
  esac
}

echo "==> pruning dangling layers"
podman image prune -f >/dev/null

echo "==> building: ${build[*]}"
podman-compose build "${build[@]}"

echo "==> recreating: ${run[*]}"
podman-compose up -d --force-recreate "${run[@]}"

echo "==> waiting for (healthy), max ${TIMEOUT_S}s"
deadline=$((SECONDS + TIMEOUT_S))
for svc in "${run[@]}"; do
  name="${PROJECT}_${svc}_1"
  until [ "$(podman inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null)" = "healthy" ]; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "ERROR: $name is not healthy:" >&2
      podman logs --tail 30 "$name" >&2 || true
      exit 1
    fi
    sleep 3
  done
  running="$(podman inspect -f '{{.Image}}' "$name")"
  built="$(podman image inspect -f '{{.Id}}' "$(image_of "$svc")")"
  if [ "$running" != "$built" ]; then
    echo "ERROR: $name runs image ${running:0:12}, the build is ${built:0:12}" >&2
    exit 1
  fi
  echo "    $name healthy, image ${built:0:12}"
done

podman image prune -f >/dev/null
podman system df | sed -n '1,2p'
echo "==> done"
