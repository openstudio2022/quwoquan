#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ECS_HOST="${GAMMA_ECS_HOST:-118.31.239.122}"
ECS_USER="${GAMMA_ECS_USER:-root}"
ECS_PORT="${GAMMA_ECS_PORT:-22}"
REMOTE_DIR="${GAMMA_ECS_REMOTE_DIR:-/opt/quwoquan/gamma}"
BASE_URL="${GAMMA_BASE_URL:-http://${ECS_HOST}:18080}"
PRODUCT_OPS_BASE_URL="${GAMMA_PRODUCT_OPS_BASE_URL:-http://${ECS_HOST}:18086}"

if [[ -z "${GAMMA_ECS_PASSWORD:-}" ]]; then
  echo "::error::GAMMA_ECS_PASSWORD is required for password-based ECS deployment" >&2
  exit 2
fi

if ! command -v sshpass >/dev/null 2>&1; then
  echo "::error::sshpass is required. Install it in CI before running this script." >&2
  exit 2
fi

export SSHPASS="$GAMMA_ECS_PASSWORD"
SSH_OPTS=(
  -p "$ECS_PORT"
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=4
)
SSH_TARGET="${ECS_USER}@${ECS_HOST}"

remote_exec() {
  sshpass -e ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"
}

echo "[gamma-ecs] target=${ECS_USER}@${ECS_HOST}:${ECS_PORT}"
echo "[gamma-ecs] remote_dir=${REMOTE_DIR}"
echo "[gamma-ecs] base_url=${BASE_URL}"
echo "[gamma-ecs] product_ops_base_url=${PRODUCT_OPS_BASE_URL}"

remote_exec "mkdir -p '$REMOTE_DIR'"

echo "[gamma-ecs] uploading repository snapshot"
tar \
  --exclude='.git' \
  --exclude='.dart_tool' \
  --exclude='build' \
  --exclude='node_modules' \
  --exclude='quwoquan_app/.dart_tool' \
  --exclude='quwoquan_app/build' \
  --exclude='apps/ops-portal/node_modules' \
  -czf - . | sshpass -e ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "tar -xzf - -C '$REMOTE_DIR'"

echo "[gamma-ecs] starting remote Docker Compose stack"
remote_exec "cd '$REMOTE_DIR' && bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

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

LOCAL_GAMMA_HTTP_PORT="${LOCAL_GAMMA_HTTP_PORT:-18000}" \
LOCAL_GAMMA_HTTPS_PORT="${LOCAL_GAMMA_HTTPS_PORT:-18443}" \
LOCAL_GAMMA_ADMIN_PORT="${LOCAL_GAMMA_ADMIN_PORT:-12019}" \
bash scripts/start_local_gamma_mirror.sh
docker compose -f quwoquan_service/docker-compose.gamma-local.yaml ps

python3 scripts/run_local_gamma_t3.py \
  --base-url http://127.0.0.1:18080 \
  --product-ops-base-url http://127.0.0.1:18086 \
  --test-auth-token "${GAMMA_TEST_AUTH_TOKEN:-gamma-ecs-token}" \
  --skip-flutter-contracts
REMOTE_SCRIPT

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

echo "[gamma-ecs] deployment completed"
