#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
DEPLOY_TARGET_ROOT="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_work_root

print(deployment_work_root("beta-local"))
PY
)"
QWQ_DEPLOY_WORK_ROOT="$(dirname "$DEPLOY_TARGET_ROOT")"
export QWQ_DEPLOY_WORK_ROOT
ACTION="${1:-up}"
if [[ "$ACTION" == "-h" || "$ACTION" == "--help" || "$ACTION" == "help" ]]; then
  cat <<'EOF'
Usage:
  quwoquan_ops/cli/beta/start_beta_stack.sh {up|down|status} [options]

Set QWQ_WORKLOAD=content-release to start only the content data plane, or
QWQ_WORKLOAD=full to include commercial telemetry, Ops services and Portal.
EOF
  exit 0
fi
eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_run.py" \
  --env beta --target beta-local --action "$ACTION" --output-root "$QWQ_OUTPUT_ROOT")"
export QWQ_OUTPUT_ROOT QWQ_DEPLOY_WORK_ROOT QWQ_OBSERVABILITY_RUN_ROOT QWQ_RUN_ROOT
RUNTIME_CONFIG_DIR="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

print(deployment_render_dir("beta", target="beta-local"))
PY
)"
STATE_DIR="${QWQ_OUTPUT_ROOT}/env/beta/local/beta-local/process"
LOG_DIR="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
ENV_FILE="${RUNTIME_CONFIG_DIR}/beta.env"
APP_BETA="$ROOT_DIR/quwoquan_app/scripts/device/start_app_beta_manual.sh"
OPS_PORTAL_DIR="$ROOT_DIR/quwoquan_ops/portal"

eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile beta-local --format shell-defaults)"
eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile gamma-local --format shell-defaults)"
eval "$(PYTHONPATH="$ROOT_DIR" python3 -m quwoquan_ops.cli.lib.local_environment_auth --shell beta beta-local)"

if [[ $# -gt 0 ]]; then
  shift
fi
GATEWAY_PORT="${GATEWAY_PORT}"
PRODUCT_OPS_PORT="${PRODUCT_OPS_PORT}"
PLATFORM_OPS_PORT="${PLATFORM_OPS_PORT}"
OPS_PORTAL_PORT="${OPS_PORTAL_PORT}"
CONTENT_PORT="${CONTENT_PORT}"
PRODUCT_OPS_SERVICE_PORT="${PRODUCT_OPS_SERVICE_PORT}"
BETA_POSTGRES_PORT="${BETA_POSTGRES_PORT}"
BETA_MONGO_PORT="${BETA_MONGO_PORT}"
BETA_REDIS_PORT="${BETA_REDIS_PORT}"
OPS_POSTGRES_DSN="${OPS_POSTGRES_DSN:-postgres://quwoquan:quwoquan@127.0.0.1:${BETA_POSTGRES_PORT}/quwoquan?sslmode=disable}"
CDN_DOMAIN="${CDN_DOMAIN:-cdn.beta.local}"
DEVICE_ID="${DEVICE_ID:-}"
START_APP="${START_APP:-1}"
SKIP_BUILD=0
AUTO_OPEN_OPS="${AUTO_OPEN_OPS:-1}"
PRODUCT_TELEMETRY_AVAILABLE="${QWQ_PRODUCT_TELEMETRY_AVAILABLE:-1}"
WORKLOAD="${QWQ_WORKLOAD:-full}"
SEED_VERIFY_MODE="${SEED_VERIFY_MODE:-}"
MEDIA_MODE="${MEDIA_MODE:-}"
LOCAL_PUBLIC_HOST="${LOCAL_PUBLIC_HOST:-}"
BETA_BACKEND_READY_TIMEOUT_SECONDS="${BETA_BACKEND_READY_TIMEOUT_SECONDS:-1200}"
MEDIA_AVATAR_BASE_URL="${MEDIA_AVATAR_BASE_URL:-}"
MEDIA_IMAGE_BASE_URL="${MEDIA_IMAGE_BASE_URL:-}"
MEDIA_VIDEO_BASE_URL="${MEDIA_VIDEO_BASE_URL:-}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-}"
GATEWAY_BASE_URL_OVERRIDE="${GATEWAY_BASE_URL_OVERRIDE:-}"
DEV_UP_HELPER="$ROOT_DIR/quwoquan_ops/cli/lib/dev_up.py"

mkdir -p "$RUNTIME_CONFIG_DIR" "$STATE_DIR" "$LOG_DIR" "$QWQ_RUN_ROOT"

usage() {
  cat <<EOF
Usage:
  quwoquan_ops/cli/beta/start_beta_stack.sh {up|down|status} [options]

Options for "up":
  --device-id <id>         指定 Flutter 设备 id；也可通过 DEVICE_ID 传入。
  --skip-app               仅启动云侧 + Ops，不启动 Flutter 端。
  --skip-build             复用已构建镜像，禁止 Compose 隐式重建。
  --with-app               显式开启 Flutter 端启动（默认开启）。
  --no-open-ops            不自动打开 Ops Portal 页面。
  --seed-verify <mode>     透传给 start_app_beta_manual.sh。
  --media-mode <mode>      透传给 start_app_beta_manual.sh。
  --local-public-host <h>  透传给 start_app_beta_manual.sh。
  --media-avatar-base-url <url>  透传头像 authority。
  --media-image-base-url <url>   透传图片 authority。
  --media-video-base-url <url>   透传视频 authority。
  --media-upload-base-url <url>  透传上传 authority。
  --gateway-base-url <u>   透传给 start_app_beta_manual.sh。
  --full-matrix            等价于 --seed-verify full --media-mode copy。
EOF
}

case "$ACTION" in
  -h|--help|help)
    usage
    exit 0
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device-id)
      DEVICE_ID="${2:-}"
      shift 2
      ;;
    --skip-app)
      START_APP=0
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --with-app)
      START_APP=1
      shift
      ;;
    --no-open-ops)
      AUTO_OPEN_OPS=0
      shift
      ;;
    --seed-verify)
      SEED_VERIFY_MODE="${2:-}"
      shift 2
      ;;
    --media-mode)
      MEDIA_MODE="${2:-}"
      shift 2
      ;;
    --local-public-host)
      LOCAL_PUBLIC_HOST="${2:-}"
      shift 2
      ;;
    --media-avatar-base-url)
      MEDIA_AVATAR_BASE_URL="${2:-}"
      shift 2
      ;;
    --media-image-base-url)
      MEDIA_IMAGE_BASE_URL="${2:-}"
      shift 2
      ;;
    --media-video-base-url)
      MEDIA_VIDEO_BASE_URL="${2:-}"
      shift 2
      ;;
    --media-upload-base-url)
      MEDIA_UPLOAD_BASE_URL="${2:-}"
      shift 2
      ;;
    --gateway-base-url)
      GATEWAY_BASE_URL_OVERRIDE="${2:-}"
      shift 2
      ;;
    --full-matrix)
      SEED_VERIFY_MODE="full"
      MEDIA_MODE="copy"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$WORKLOAD" in
  content-release)
    # 内容导入与消费只依赖内容数据面；商业观测和运营控制面只属于 full。
    PRODUCT_TELEMETRY_AVAILABLE=0
    AUTO_OPEN_OPS=0
    ;;
  full)
    if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
      echo "GATE_BLOCK: beta full workload requires product telemetry; use QWQ_WORKLOAD=content-release for the content data plane." >&2
      exit 2
    fi
    ;;
  *)
    echo "GATE_BLOCK: unsupported beta workload: $WORKLOAD" >&2
    exit 2
    ;;
esac

if ! [[ "$BETA_BACKEND_READY_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "GATE_BLOCK: BETA_BACKEND_READY_TIMEOUT_SECONDS must be a positive integer." >&2
  exit 2
fi

write_env() {
  cat > "$ENV_FILE" <<EOF
APP_RUNTIME_ENV=beta
APP_DATA_SOURCE=remote
CDN_DOMAIN=${CDN_DOMAIN}
GATEWAY_BASE_URL=https://beta-api.quwoquan-env.test:${GATEWAY_PORT}
PRODUCT_OPS_BASE_URL=https://beta-product-ops.quwoquan-env.test:${PRODUCT_OPS_PORT}
PLATFORM_OPS_BASE_URL=http://127.0.0.1:${PLATFORM_OPS_PORT}
OPS_PORTAL_BASE_URL=http://127.0.0.1:${OPS_PORTAL_PORT}
OBSERVABILITY_BASE_URL=http://127.0.0.1:9200
RECOMMENDATION_BASE_URL=http://127.0.0.1:${CONTENT_PORT}
EOF
}

start_bg() {
  local name="$1"
  shift
  python3 - "$STATE_DIR/${name}.pid" "$STATE_DIR/${name}.pgid" \
    "$ROOT_DIR/quwoquan_ops/cli/lib/runtime_log_process.py" \
    "$LOG_DIR/${name}/local/runtime.log" "$name" "$@" <<'PY'
import os
import subprocess
import sys
from pathlib import Path

pid_path = Path(sys.argv[1])
pgid_path = Path(sys.argv[2])
wrapper = sys.argv[3]
log_path = sys.argv[4]
event = sys.argv[5]
argv = sys.argv[6:]
diagnostic_log = pid_path.parent / "stdout" / f"{event}.log"
proc = subprocess.Popen(
    [
        sys.executable,
        wrapper,
        "--log-file",
        log_path,
        "--diagnostic-log",
        str(diagnostic_log),
        "--event",
        event,
        "--",
        *argv,
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
    start_new_session=True,
)
pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
pgid_path.write_text(f"{os.getpgid(proc.pid)}\n", encoding="utf-8")
PY
  local pid pgid
  pid="$(cat "$STATE_DIR/${name}.pid")"
  pgid="$(cat "$STATE_DIR/${name}.pgid")"
  echo "[beta] started ${name} pid=${pid} pgid=${pgid}"
}

stop_bg() {
  local name="$1"
  local pgid_file="$STATE_DIR/${name}.pgid"
  local pid_file="$STATE_DIR/${name}.pid"
  local pid=""
  local pgid=""
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
  fi
  if [[ -f "$pgid_file" ]]; then
    pgid="$(cat "$pgid_file")"
  fi
  if [[ -n "$pid" || -n "$pgid" ]]; then
    if [[ -n "$pgid" ]] && kill -0 "-$pgid" >/dev/null 2>&1; then
      kill -TERM "-$pgid" >/dev/null 2>&1 || true
      local deadline=$((SECONDS + 20))
      while kill -0 "-$pgid" >/dev/null 2>&1; do
        if (( SECONDS >= deadline )); then
          kill -KILL "-$pgid" >/dev/null 2>&1 || true
          break
        fi
        sleep 0.2
      done
      echo "[beta] stopped ${name} pgid=${pgid}"
    elif [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      echo "[beta] stopped ${name} pid=${pid}"
    fi
  fi
  rm -f "$pid_file" "$pgid_file"
}

status_one() {
  local name="$1"
  local url="$2"
  if [[ -f "$STATE_DIR/${name}.pid" ]] && kill -0 "$(cat "$STATE_DIR/${name}.pid")" >/dev/null 2>&1; then
    echo "[beta] ${name}: running pid=$(cat "$STATE_DIR/${name}.pid")"
  elif [[ -f "$STATE_DIR/${name}.pgid" ]] && kill -0 "-$(cat "$STATE_DIR/${name}.pgid")" >/dev/null 2>&1; then
    echo "[beta] ${name}: running pgid=$(cat "$STATE_DIR/${name}.pgid")"
  else
    echo "[beta] ${name}: not-running"
  fi
  if command -v curl >/dev/null 2>&1; then
    wait_http_ok "$url" 3 >/dev/null 2>&1 && echo "[beta] ${name}: health ok ${url}" || echo "[beta] ${name}: health pending ${url}"
  fi
}

wait_http_ok() {
  local url="$1"
  local timeout="${2:-30}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS "$url" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 0.5
  done
}

wait_service_ok() {
  local name="$1"
  local url="$2"
  local timeout="${3:-45}"
  local deadline=$((SECONDS + timeout))
  local pid_file="$STATE_DIR/${name}.pid"
  local log_file="$LOG_DIR/${name}/local/runtime.log"
  while ! curl -fsS "$url" >/dev/null 2>&1; do
    if [[ -f "$pid_file" ]] && ! kill -0 "$(cat "$pid_file")" >/dev/null 2>&1; then
      echo "[beta] ${name} exited before readiness: ${url}" >&2
      if [[ -f "$log_file" ]]; then
        tail -20 "$log_file" >&2
      fi
      return 1
    fi
    if (( SECONDS >= deadline )); then
      echo "[beta] ${name} not ready within ${timeout}s: ${url}" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "[beta] ${name} ready: ${url}"
}

maybe_open_ops() {
  local url="http://127.0.0.1:${OPS_PORTAL_PORT}/"
  if [[ "$AUTO_OPEN_OPS" != "1" ]]; then
    return 0
  fi
  if wait_http_ok "$url" 30; then
    echo "[beta] ops-portal ready: $url"
    if command -v open >/dev/null 2>&1; then
      open "$url" >/dev/null 2>&1 || true
      echo "[beta] opened ops portal in browser"
    else
      echo "[beta] open ops portal manually: $url"
    fi
  else
    echo "[beta] ops-portal not ready yet, open manually later: $url"
  fi
}

build_app_beta_command() {
  APP_BETA_CMD=(
    env
    QWQ_OUTPUT_ROOT="$QWQ_OUTPUT_ROOT"
    QWQ_OBSERVABILITY_RUN_ROOT="$QWQ_OBSERVABILITY_RUN_ROOT"
    QWQ_RUN_ROOT="$QWQ_RUN_ROOT"
    CDN_DOMAIN="${CDN_DOMAIN}"
    "$APP_BETA"
    --restart
  )
  if [[ "$START_APP" != "1" ]]; then
    APP_BETA_CMD+=(--skip-app)
  fi
  if [[ "$SKIP_BUILD" == "1" ]]; then
    APP_BETA_CMD+=(--skip-build)
  fi
  if [[ "$WORKLOAD" == "content-release" ]]; then
    APP_BETA_CMD+=(--content-release)
  fi
  if [[ -n "$DEVICE_ID" ]]; then
    APP_BETA_CMD+=(--device-id "$DEVICE_ID")
  fi
  if [[ -n "$SEED_VERIFY_MODE" ]]; then
    APP_BETA_CMD+=(--seed-verify "$SEED_VERIFY_MODE")
  fi
  if [[ -n "$MEDIA_MODE" ]]; then
    APP_BETA_CMD+=(--media-mode "$MEDIA_MODE")
  fi
  if [[ -n "$LOCAL_PUBLIC_HOST" ]]; then
    APP_BETA_CMD+=(--local-public-host "$LOCAL_PUBLIC_HOST")
  fi
  if [[ -n "$MEDIA_AVATAR_BASE_URL" ]]; then
    APP_BETA_CMD+=(--media-avatar-base-url "$MEDIA_AVATAR_BASE_URL")
  fi
  if [[ -n "$MEDIA_IMAGE_BASE_URL" ]]; then
    APP_BETA_CMD+=(--media-image-base-url "$MEDIA_IMAGE_BASE_URL")
  fi
  if [[ -n "$MEDIA_VIDEO_BASE_URL" ]]; then
    APP_BETA_CMD+=(--media-video-base-url "$MEDIA_VIDEO_BASE_URL")
  fi
  if [[ -n "$MEDIA_UPLOAD_BASE_URL" ]]; then
    APP_BETA_CMD+=(--media-upload-base-url "$MEDIA_UPLOAD_BASE_URL")
  fi
  if [[ -n "$GATEWAY_BASE_URL_OVERRIDE" ]]; then
    APP_BETA_CMD+=(--gateway-base-url "$GATEWAY_BASE_URL_OVERRIDE")
  fi
}

resolve_device_id_if_needed() {
  if [[ "$START_APP" != "1" || -n "$DEVICE_ID" ]]; then
    return 0
  fi
  DEVICE_ID="$(python3 "$DEV_UP_HELPER" pick-device --app-dir "$ROOT_DIR/quwoquan_app")"
  if [[ -z "$DEVICE_ID" ]]; then
    echo "GATE_BLOCK: failed to resolve Flutter device id for beta launch." >&2
    exit 2
  fi
  echo "[beta] selected Flutter device: $DEVICE_ID"
}

case "$ACTION" in
  up)
    write_env
    echo "[beta] wrote $ENV_FILE"
    stop_bg ops-portal
    stop_bg product-ops
    stop_bg platform-ops
    stop_bg app-beta
    if [[ "$START_APP" == "1" ]]; then
      resolve_device_id_if_needed
    fi
    # `app-beta` owns the local beta gateway/chat/assistant stack. When START_APP=0
    # we still launch it in `--skip-app` backend-only mode so stackctl can keep the
    # beta services alive while launching Flutter separately.
    build_app_beta_command
    start_bg app-beta "${APP_BETA_CMD[@]}"
    # 冷缓存下 `docker compose up --build` 会先完成 Go 镜像构建，再创建内容数据面。
    # 不能把构建期误报为后端不可用；仍保留可配置且有上界语义的 readiness 失败。
    wait_service_ok app-beta "http://127.0.0.1:${CONTENT_PORT}/healthz" "$BETA_BACKEND_READY_TIMEOUT_SECONDS" || {
      echo "[beta] app-beta backend did not become ready" >&2
      exit 1
    }
    if [[ "$WORKLOAD" == "full" ]]; then
      start_bg platform-ops bash -lc "cd '$ROOT_DIR/quwoquan_service/control-plane/platform-ops' && REPO_ROOT='$ROOT_DIR' QWQ_OUTPUT_ROOT='$QWQ_OUTPUT_ROOT' APP_ENV='beta' POSTGRES_DSN='$OPS_POSTGRES_DSN' AUTH_JWT_SECRET='$AUTH_JWT_SECRET' AUTH_JWT_ISSUER='$AUTH_JWT_ISSUER' AUTH_JWT_AUDIENCE='$AUTH_JWT_AUDIENCE' AUTH_JWT_TOKEN_VERSION='$AUTH_JWT_TOKEN_VERSION' PLATFORM_OPS_SERVICE_ADDR='127.0.0.1:${PLATFORM_OPS_PORT}' go run ./cmd/api"
      wait_service_ok platform-ops "http://127.0.0.1:${PLATFORM_OPS_PORT}/healthz" 60
      start_bg product-ops bash -lc "cd '$ROOT_DIR/quwoquan_service/services/product-ops-service' && REPO_ROOT='$ROOT_DIR' QWQ_OUTPUT_ROOT='$QWQ_OUTPUT_ROOT' APP_ENV='beta' POSTGRES_DSN='$OPS_POSTGRES_DSN' MONGODB_URI='mongodb://127.0.0.1:${BETA_MONGO_PORT}/?directConnection=true' MONGODB_DATABASE='quwoquan_product_ops' REDIS_GENERAL_ADDR='127.0.0.1:${BETA_REDIS_PORT}' REDIS_REC_ADDR='127.0.0.1:${BETA_REDIS_PORT}' AUTH_JWT_SECRET='$AUTH_JWT_SECRET' AUTH_JWT_ISSUER='$AUTH_JWT_ISSUER' AUTH_JWT_AUDIENCE='$AUTH_JWT_AUDIENCE' AUTH_JWT_TOKEN_VERSION='$AUTH_JWT_TOKEN_VERSION' AUTH_DEVICE_TICKET_SECRET='$AUTH_DEVICE_TICKET_SECRET' AUTH_DEVICE_TICKET_ISSUER='$AUTH_DEVICE_TICKET_ISSUER' AUTH_DEVICE_TICKET_AUDIENCE='$AUTH_DEVICE_TICKET_AUDIENCE' AUTH_DEVICE_TICKET_TOKEN_VERSION='$AUTH_DEVICE_TICKET_TOKEN_VERSION' PRODUCT_OPS_SERVICE_ADDR='127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}' PLATFORM_OPS_BASE_URL='http://127.0.0.1:${PLATFORM_OPS_PORT}' go run ./cmd/api"
      wait_service_ok product-ops "http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}/healthz" 60
      start_bg ops-portal env VITE_PRODUCT_OPS_BASE_URL="http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}" VITE_PLATFORM_OPS_BASE_URL="http://127.0.0.1:${PLATFORM_OPS_PORT}" VITE_GATEWAY_BASE_URL="http://127.0.0.1:${CONTENT_PORT}" npm --prefix "$OPS_PORTAL_DIR" run dev -- --host 127.0.0.1 --port "${OPS_PORTAL_PORT}"
      wait_service_ok ops-portal "http://127.0.0.1:${OPS_PORTAL_PORT}/" 60
      maybe_open_ops
      status_one product-ops "http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}/healthz"
      status_one platform-ops "http://127.0.0.1:${PLATFORM_OPS_PORT}/healthz"
      status_one ops-portal "http://127.0.0.1:${OPS_PORTAL_PORT}/"
    else
      echo "[beta] workload=content-release; product-ops, platform-ops and ops-portal are not started."
    fi
    status_one app-beta "http://127.0.0.1:${CONTENT_PORT}/healthz"
    ;;
  down)
    stop_bg app-beta
    stop_bg ops-portal
    stop_bg product-ops
    stop_bg platform-ops
    ;;
  status)
    [[ -f "$ENV_FILE" ]] && echo "[beta] env: $ENV_FILE" || echo "[beta] env: missing"
    echo "[beta] app launch: $([[ "$START_APP" == "1" ]] && echo enabled || echo disabled)${DEVICE_ID:+ device=$DEVICE_ID}"
    status_one app-beta "http://127.0.0.1:${CONTENT_PORT}/healthz"
    status_one product-ops "http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}/healthz"
    status_one platform-ops "http://127.0.0.1:${PLATFORM_OPS_PORT}/healthz"
    status_one ops-portal "http://127.0.0.1:${OPS_PORTAL_PORT}/"
    status_one gateway "http://127.0.0.1:${CONTENT_PORT}/healthz"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
