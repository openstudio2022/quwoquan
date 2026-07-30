#!/usr/bin/env bash
set -euo pipefail

KEY_DIR="${PROD_SSH_KEY_DIR:-$HOME/.ssh/quwoquan-prod}"
HOST="${PROD_SSH_HOST:-}"
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
[[ -n "$HOST" ]] || { echo "FAIL: --host or PROD_SSH_HOST is required" >&2; exit 2; }
KEY_FILE="${KEY_DIR%/}/${ACCOUNT}"
[[ -f "$KEY_FILE" ]] || { echo "FAIL: missing key file: $KEY_FILE" >&2; exit 2; }

REMOTE_CMD="set -euo pipefail
cd '${WORKSPACE_ROOT}'
export QWQ_COMPOSE_ALPINE_BASE_IMAGE='docker.io/library/debian:bookworm-slim'
export QWQ_COMPOSE_ENV=prod
export QWQ_COMPOSE_CONFIG_ROOT=/tmp/qwq-config
export QWQ_COMPOSE_REC_POLICY_SOURCE=/dev/null
export QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT=http://127.0.0.1
export QWQ_COMPOSE_OBJECT_STORAGE_BUCKET=build-only
export QWQ_COMPOSE_OBJECT_STORAGE_REGION=build-only
export QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID=build-only
export QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET=build-only
export QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL=https://cdn.example.invalid
export QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL=https://upload.example.invalid
export QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY=build-only
for svc in ${SERVICES//,/ }; do
  echo \"[remote-build] \$svc\"
  fragment=\"quwoquan_service/services/\${svc}/deploy/compose.yaml\"
  if [[ ! -f \"\$fragment\" ]]; then
    echo \"FAIL: autonomous compose fragment missing: \$fragment\" >&2
    exit 1
  fi
  version_var=\"QWQ_COMPOSE_\$(printf '%s' \"\$svc\" | tr '[:lower:]-' '[:upper:]_')_CONFIG_VERSION\"
  printf -v \"\$version_var\" '%s' 'sha256:0000000000000000000000000000000000000000000000000000000000000000'
  export \"\$version_var\"
  podman compose \
    -f quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml \
    -f \"\$fragment\" \
    build \"\$svc\"
  # podman compose 是薄壳，build 失败的退出码不一定冒泡；用镜像存在性硬校验。
  image_ref=\"localhost/quwoquan_service_\${svc}:latest\"
  if ! podman image exists \"\$image_ref\"; then
    echo \"FAIL: remote build produced no image: \$image_ref\" >&2
    exit 1
  fi
done"

ssh -i "$KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=no "${ACCOUNT}@${HOST}" "$REMOTE_CMD"
