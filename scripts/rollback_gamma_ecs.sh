#!/usr/bin/env bash
# 一键回滚：恢复远端最近一次 deploy_gamma_ecs.sh 生成的备份 tarball，并重启 compose。
# 需与 deploy 相同的 SSH 认证（GAMMA_ECS_SSH_KEY 或 GAMMA_ECS_PASSWORD）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ECS_HOST="${GAMMA_ECS_HOST:-118.31.239.122}"
ECS_USER="${GAMMA_ECS_USER:-root}"
ECS_PORT="${GAMMA_ECS_PORT:-22}"
REMOTE_DIR="${GAMMA_ECS_REMOTE_DIR:-/opt/quwoquan/gamma}"
BACKUP_PARENT="${GAMMA_ECS_BACKUP_PARENT:-${REMOTE_DIR}/../gamma-backups}"
PICK="${GAMMA_ECS_ROLLBACK_BACKUP:-}"

SSH_OPTS=(
  -p "$ECS_PORT"
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=4
)
SSH_TARGET="${ECS_USER}@${ECS_HOST}"
TMP_KEY_FILE=""

cleanup() {
  if [[ -n "${TMP_KEY_FILE:-}" && -f "${TMP_KEY_FILE:-}" ]]; then
    rm -f "$TMP_KEY_FILE"
  fi
}
trap cleanup EXIT

remote_exec() {
  if [[ -n "${TMP_KEY_FILE:-}" ]]; then
    ssh "${SSH_OPTS[@]}" -i "$TMP_KEY_FILE" "$SSH_TARGET" "$@"
  else
    sshpass -e ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"
  fi
}

if [[ -n "${GAMMA_ECS_SSH_KEY:-}" ]]; then
  TMP_KEY_FILE="$(mktemp)"
  printf '%s\n' "$GAMMA_ECS_SSH_KEY" >"$TMP_KEY_FILE"
  chmod 600 "$TMP_KEY_FILE"
elif [[ -n "${GAMMA_ECS_PASSWORD:-}" ]]; then
  export SSHPASS="$GAMMA_ECS_PASSWORD"
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "::error::sshpass is required when using GAMMA_ECS_PASSWORD" >&2
    exit 2
  fi
else
  echo "::error::Set GAMMA_ECS_SSH_KEY or GAMMA_ECS_PASSWORD" >&2
  exit 2
fi

echo "[gamma-ecs-rollback] backup_parent=${BACKUP_PARENT}"
remote_exec "bash -s" <<REMOTE
set -euo pipefail
BACKUP_PARENT='${BACKUP_PARENT}'
REMOTE_DIR='${REMOTE_DIR}'
PICK='${PICK}'
mkdir -p "\${BACKUP_PARENT}"
if [ -n "\${PICK}" ]; then
  BACKUP="\${PICK}"
else
  BACKUP="\$(ls -1t "\${BACKUP_PARENT}"/backup-*.tgz 2>/dev/null | head -n1 || true)"
fi
if [ -z "\${BACKUP:-}" ] || [ ! -f "\${BACKUP}" ]; then
  echo "[gamma-ecs-rollback] no backup tarball under \${BACKUP_PARENT}" >&2
  exit 2
fi
echo "[gamma-ecs-rollback] restoring \${BACKUP} -> \${REMOTE_DIR}"
rm -rf "\${REMOTE_DIR}"
mkdir -p "\${REMOTE_DIR}"
tar -xzf "\${BACKUP}" -C "\${REMOTE_DIR}"
cd "\${REMOTE_DIR}"
export LOCAL_GAMMA_HTTP_PORT="\${LOCAL_GAMMA_HTTP_PORT:-18000}"
export LOCAL_GAMMA_HTTPS_PORT="\${LOCAL_GAMMA_HTTPS_PORT:-18443}"
export LOCAL_GAMMA_ADMIN_PORT="\${LOCAL_GAMMA_ADMIN_PORT:-12019}"
bash scripts/start_local_gamma_mirror.sh
docker compose -f quwoquan_service/docker-compose.gamma-local.yaml ps
REMOTE

echo "[gamma-ecs-rollback] rollback completed"
