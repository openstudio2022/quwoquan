#!/usr/bin/env bash
set -euo pipefail

KEY_DIR="${PROD_SSH_KEY_DIR:-$HOME/.ssh/quwoquan-prod}"
HOST="${PROD_SSH_HOST:-118.31.239.122}"
ACCOUNT="prod-service-svc"
WORKSPACE_ROOT="/home/${ACCOUNT}/bootstrap/prod-build-workspace"
SERVICES=""

usage() {
  cat <<'EOF'
Usage: build_prod_plane_images_remote.sh --services <csv> [--host <host>] [--key-dir <dir>] [--workspace-root <path>]

Build prod service-plane images natively on the remote x86_64 host via podman compose.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --services) SERVICES="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --key-dir) KEY_DIR="$2"; shift 2 ;;
    --workspace-root) WORKSPACE_ROOT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "FAIL: unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$SERVICES" ]] || { echo "FAIL: --services is required" >&2; exit 2; }
KEY_FILE="${KEY_DIR%/}/${ACCOUNT}"
[[ -f "$KEY_FILE" ]] || { echo "FAIL: missing key file: $KEY_FILE" >&2; exit 2; }

REMOTE_CMD="set -euo pipefail
cd '${WORKSPACE_ROOT}/quwoquan_service'
export LOCAL_GAMMA_ALPINE_BASE_IMAGE='docker.io/library/debian:bookworm-slim'
for svc in ${SERVICES//,/ }; do
  echo \"[remote-build] \$svc\"
  podman compose -f docker-compose.gamma-local.yaml build \"\$svc\"
done"

ssh -i "$KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=no "${ACCOUNT}@${HOST}" "$REMOTE_CMD"
