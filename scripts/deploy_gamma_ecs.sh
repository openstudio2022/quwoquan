#!/usr/bin/env bash
# ECS Onebox：预发布(pre) / 生产就地升级(prod) 共用同一 REMOTE_DIR 与同端口栈。
# 认证：GAMMA_ECS_SSH_KEY（私钥全文）或 GAMMA_ECS_PASSWORD（sshpass）。
# 版本：GAMMA_DEPLOY_IMAGE_VERSION → 远端 LOCAL_GAMMA_IMAGE_VERSION（写入 compose 构建/运行元数据）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ECS_HOST="${GAMMA_ECS_HOST:-118.31.239.122}"
ECS_USER="${GAMMA_ECS_USER:-root}"
ECS_PORT="${GAMMA_ECS_PORT:-22}"
REMOTE_DIR="${GAMMA_ECS_REMOTE_DIR:-/opt/quwoquan/gamma}"
BASE_URL="${GAMMA_BASE_URL:-http://${ECS_HOST}:18080}"
PRODUCT_OPS_BASE_URL="${GAMMA_PRODUCT_OPS_BASE_URL:-http://${ECS_HOST}:18086}"
STAGE="${GAMMA_ECS_STAGE:-pre}"
SKIP_UPLOAD="${GAMMA_ECS_SKIP_UPLOAD:-0}"
IMAGE_VERSION="${GAMMA_DEPLOY_IMAGE_VERSION:-$(git rev-parse --short HEAD 2>/dev/null || echo manual)}"
LOCAL_TARBALL="${GAMMA_ECS_LOCAL_TARBALL:-}"
REPORT_DIR="${ROOT}/artifacts/ecs-onebox"
REPORT_PATH="${REPORT_DIR}/deploy-report.json"
BACKUP_PARENT="${GAMMA_ECS_BACKUP_PARENT:-}"

SSH_OPTS=(
  -p "$ECS_PORT"
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=4
)
SSH_TARGET="${ECS_USER}@${ECS_HOST}"
TMP_KEY_FILE=""
SSHPASS_PID=""

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

remote_tar_extract() {
  # stdin: tarball bytes
  if [[ -n "${TMP_KEY_FILE:-}" ]]; then
    ssh "${SSH_OPTS[@]}" -i "$TMP_KEY_FILE" "$SSH_TARGET" "mkdir -p '$REMOTE_DIR' && tar -xzf - -C '$REMOTE_DIR'"
  else
    sshpass -e ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_DIR' && tar -xzf - -C '$REMOTE_DIR'"
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
  echo "::error::Set GAMMA_ECS_SSH_KEY or GAMMA_ECS_PASSWORD for ECS deployment" >&2
  exit 2
fi

mkdir -p "$REPORT_DIR"
STARTED_AT="$(python3 - <<'PY'
import datetime as dt
print(dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"))
PY
)"

echo "[gamma-ecs] stage=${STAGE}"
echo "[gamma-ecs] target=${ECS_USER}@${ECS_HOST}:${ECS_PORT}"
echo "[gamma-ecs] remote_dir=${REMOTE_DIR}"
echo "[gamma-ecs] base_url=${BASE_URL}"
echo "[gamma-ecs] product_ops_base_url=${PRODUCT_OPS_BASE_URL}"
echo "[gamma-ecs] image_version=${IMAGE_VERSION}"
echo "[gamma-ecs] skip_upload=${SKIP_UPLOAD}"

FAILURE_STAGE=""
on_fail() {
  FAILURE_STAGE="${FAILURE_STAGE:-unknown}"
  python3 - "$REPORT_PATH" "$STARTED_AT" "$STAGE" "$IMAGE_VERSION" "$BASE_URL" "$FAILURE_STAGE" <<'PY' || true
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path, started, stage, image_version, base_url, failure_stage = sys.argv[1:7]
report = {
    "startedAt": started,
    "endedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": "failed",
    "stage": stage,
    "imageVersion": image_version,
    "baseUrl": base_url,
    "failureStage": failure_stage,
}
Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[gamma-ecs] deploy report written: {path}")
PY
}
trap 'on_fail' ERR

BACKUP_REMOTE="${BACKUP_PARENT:-$REMOTE_DIR/../gamma-backups}"
echo "[gamma-ecs] remote_backup_parent=${BACKUP_REMOTE}"

if [[ "$SKIP_UPLOAD" != "1" ]]; then
  echo "[gamma-ecs] creating remote backup snapshot (if tree exists)"
  FAILURE_STAGE="backup"
  remote_exec "mkdir -p '$BACKUP_REMOTE'"
  remote_exec "if [ -f '$REMOTE_DIR/quwoquan_service/docker-compose.gamma-local.yaml' ]; then ts=\$(date +%Y%m%d%H%M%S); tar -czf '$BACKUP_REMOTE/backup-\${ts}.tgz' -C '$REMOTE_DIR' .; echo '[gamma-ecs] backup saved to $BACKUP_REMOTE/backup-'\$ts'.tgz'; fi"

  echo "[gamma-ecs] uploading repository snapshot"
  FAILURE_STAGE="upload"
  if [[ -n "$LOCAL_TARBALL" ]]; then
    if [[ ! -f "$LOCAL_TARBALL" ]]; then
      echo "::error::GAMMA_ECS_LOCAL_TARBALL not found: $LOCAL_TARBALL" >&2
      exit 2
    fi
    remote_exec "mkdir -p '$REMOTE_DIR'"
    if [[ -n "${TMP_KEY_FILE:-}" ]]; then
      scp "${SSH_OPTS[@]}" -i "$TMP_KEY_FILE" "$LOCAL_TARBALL" "$SSH_TARGET:$REMOTE_DIR/.incoming-repo.tgz"
    else
      sshpass -e scp "${SSH_OPTS[@]}" "$LOCAL_TARBALL" "$SSH_TARGET:$REMOTE_DIR/.incoming-repo.tgz"
    fi
    remote_exec "tar -xzf '$REMOTE_DIR/.incoming-repo.tgz' -C '$REMOTE_DIR' && rm -f '$REMOTE_DIR/.incoming-repo.tgz'"
  else
    tar \
      --exclude='.git' \
      --exclude='.dart_tool' \
      --exclude='build' \
      --exclude='node_modules' \
      --exclude='quwoquan_app/.dart_tool' \
      --exclude='quwoquan_app/build' \
      --exclude='apps/ops-portal/node_modules' \
      -czf - . | remote_tar_extract
  fi
else
  echo "[gamma-ecs] skip_upload=1 — using existing tree at ${REMOTE_DIR}"
fi

FAILURE_STAGE="remote_compose"
echo "[gamma-ecs] persisting deploy state & starting stack (LOCAL_GAMMA_IMAGE_VERSION=${IMAGE_VERSION})"

PREV_IMAGE_VERSION=""
if remote_exec "test -f '${REMOTE_DIR}/.gamma_deploy_state.json'"; then
  PREV_IMAGE_VERSION="$(
    remote_exec "python3 -c \"import json, pathlib; p=pathlib.Path('${REMOTE_DIR}/.gamma_deploy_state.json'); print(json.loads(p.read_text(encoding='utf-8')).get('imageVersion',''))\"" 2>/dev/null || true
  )"
fi

remote_exec "cd '${REMOTE_DIR}' && export PREV_IMAGE_VERSION=$(printf '%q' "$PREV_IMAGE_VERSION") IMAGE_VERSION=$(printf '%q' "$IMAGE_VERSION") STAGE=$(printf '%q' "$STAGE") GAMMA_TEST_AUTH_TOKEN=$(printf '%q' "${GAMMA_TEST_AUTH_TOKEN:-gamma-ecs-token}") && bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
python3 - <<'PY'
import json
import os
from pathlib import Path
from datetime import datetime, timezone

remote_dir = Path.cwd()
path = remote_dir / ".gamma_deploy_state.json"
prev = os.environ.get("PREV_IMAGE_VERSION", "").strip() or None
data = {
    "previousImageVersion": prev,
    "imageVersion": os.environ["IMAGE_VERSION"],
    "stage": os.environ["STAGE"],
    "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

install_docker_if_needed() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    :
  fi

  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update
      apt-get install -y ca-certificates curl gnupg lsb-release python3
    elif command -v yum >/dev/null 2>&1; then
      yum install -y ca-certificates curl python3
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y ca-certificates curl python3
    fi
  elif ! command -v python3 >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update
      apt-get install -y python3
    elif command -v yum >/dev/null 2>&1; then
      yum install -y python3
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y python3
    fi
  fi

  if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
  fi

  systemctl enable docker >/dev/null 2>&1 || true
  systemctl start docker >/dev/null 2>&1 || true

  if ! docker compose version >/dev/null 2>&1; then
    mkdir -p /usr/local/lib/docker/cli-plugins
    arch="$(uname -m)"
    case "$arch" in
      x86_64|amd64) compose_arch="x86_64" ;;
      aarch64|arm64) compose_arch="aarch64" ;;
      *) echo "unsupported architecture for docker compose: $arch" >&2; exit 2 ;;
    esac
    curl -fsSL "https://github.com/docker/compose/releases/download/v2.27.1/docker-compose-linux-${compose_arch}" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  fi
}

install_docker_if_needed
docker --version
docker compose version

export LOCAL_GAMMA_IMAGE_VERSION="${IMAGE_VERSION}"
export LOCAL_GAMMA_HTTP_PORT="${LOCAL_GAMMA_HTTP_PORT:-18000}"
export LOCAL_GAMMA_HTTPS_PORT="${LOCAL_GAMMA_HTTPS_PORT:-18443}"
export LOCAL_GAMMA_ADMIN_PORT="${LOCAL_GAMMA_ADMIN_PORT:-12019}"

bash scripts/start_local_gamma_mirror.sh
docker compose -f quwoquan_service/docker-compose.gamma-local.yaml ps

python3 scripts/run_local_gamma_t3.py \
  --base-url http://127.0.0.1:18080 \
  --product-ops-base-url http://127.0.0.1:18086 \
  --test-auth-token "${GAMMA_TEST_AUTH_TOKEN:-gamma-ecs-token}" \
  --skip-flutter-contracts
REMOTE_SCRIPT

FAILURE_STAGE="public_health"
echo "[gamma-ecs] verifying public endpoints"
python3 - "$BASE_URL" "$PRODUCT_OPS_BASE_URL" <<'PY'
import sys
import time
import urllib.request

base_url = sys.argv[1].rstrip("/")
ops_url = sys.argv[2].rstrip("/")

def wait(url: str) -> None:
    deadline = time.time() + 90
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 300:
                    print(f"[gamma-ecs] OK {url} -> {response.status}")
                    return
                last = f"http {response.status}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(2)
    raise SystemExit(f"[gamma-ecs] endpoint not ready: {url}: {last}")

wait(base_url + "/healthz")
wait(ops_url + "/healthz")
PY

python3 - "$REPORT_PATH" "$STARTED_AT" "$STAGE" "$IMAGE_VERSION" "$BASE_URL" "$PRODUCT_OPS_BASE_URL" "$REMOTE_DIR" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path, started, stage, image_version, base_url, ops_url, remote_dir = sys.argv[1:8]
report = {
    "startedAt": started,
    "endedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": "passed",
    "stage": stage,
    "imageVersion": image_version,
    "baseUrl": base_url,
    "productOpsBaseUrl": ops_url,
    "remoteDir": remote_dir,
    "failureStage": None,
}
Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[gamma-ecs] deploy report written: {path}")
PY

trap - ERR
echo "[gamma-ecs] deployment completed (${STAGE})"
