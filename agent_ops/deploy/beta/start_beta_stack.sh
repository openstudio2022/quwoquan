#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STATE_DIR="$ROOT_DIR/tmp/beta_stack"
ENV_FILE="$ROOT_DIR/.env.beta.local"
APP_BETA="$ROOT_DIR/quwoquan_app/scripts/device/start_app_beta_manual.sh"
OPS_PORTAL_DIR="$ROOT_DIR/apps/ops-portal"

ACTION="${1:-up}"
if [[ $# -gt 0 ]]; then
  shift
fi
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
PRODUCT_OPS_PORT="${PRODUCT_OPS_PORT:-18091}"
PLATFORM_OPS_PORT="${PLATFORM_OPS_PORT:-18092}"
OPS_PORTAL_PORT="${OPS_PORTAL_PORT:-18100}"
CDN_DOMAIN="${CDN_DOMAIN:-cdn.beta.local}"
DEVICE_ID="${DEVICE_ID:-}"
START_APP="${START_APP:-1}"
AUTO_OPEN_OPS="${AUTO_OPEN_OPS:-1}"
SEED_VERIFY_MODE="${SEED_VERIFY_MODE:-}"
MEDIA_MODE="${MEDIA_MODE:-}"
LOCAL_PUBLIC_HOST="${LOCAL_PUBLIC_HOST:-}"
MEDIA_BASE_URL="${MEDIA_BASE_URL:-}"
GATEWAY_BASE_URL_OVERRIDE="${GATEWAY_BASE_URL_OVERRIDE:-}"
DEVICE_DISCOVERY_SCRIPT="$ROOT_DIR/quwoquan_app/scripts/device/discover_flutter_mobile_devices.py"

mkdir -p "$STATE_DIR"

usage() {
  cat <<EOF
Usage:
  agent_ops/deploy/beta/start_beta_stack.sh {up|down|status} [options]

Options for "up":
  --device-id <id>         指定 Flutter 设备 id；也可通过 DEVICE_ID 传入。
  --skip-app               仅启动云侧 + Ops，不启动 Flutter 端。
  --with-app               显式开启 Flutter 端启动（默认开启）。
  --no-open-ops            不自动打开 Ops Portal 页面。
  --seed-verify <mode>     透传给 start_app_beta_manual.sh。
  --media-mode <mode>      透传给 start_app_beta_manual.sh。
  --local-public-host <h>  透传给 start_app_beta_manual.sh。
  --media-base-url <url>   透传给 start_app_beta_manual.sh。
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
    --media-base-url)
      MEDIA_BASE_URL="${2:-}"
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

write_env() {
  cat > "$ENV_FILE" <<EOF
APP_RUNTIME_ENV=beta
APP_DATA_SOURCE=remote
CDN_DOMAIN=${CDN_DOMAIN}
GATEWAY_BASE_URL=http://127.0.0.1:${GATEWAY_PORT}
PRODUCT_OPS_BASE_URL=http://127.0.0.1:${PRODUCT_OPS_PORT}
PLATFORM_OPS_BASE_URL=http://127.0.0.1:${PLATFORM_OPS_PORT}
OPS_PORTAL_BASE_URL=http://127.0.0.1:${OPS_PORTAL_PORT}
OBSERVABILITY_BASE_URL=http://127.0.0.1:9200
RECOMMENDATION_BASE_URL=http://127.0.0.1:${GATEWAY_PORT}
EOF
}

start_bg() {
  local name="$1"
  shift
  python3 - "$STATE_DIR/${name}.pid" "$STATE_DIR/${name}.pgid" "$STATE_DIR/${name}.log" "$@" <<'PY'
import os
import subprocess
import sys
from pathlib import Path

pid_path = Path(sys.argv[1])
pgid_path = Path(sys.argv[2])
log_path = Path(sys.argv[3])
argv = sys.argv[4:]

log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("ab", buffering=0) as log:
    proc = subprocess.Popen(
        argv,
        stdout=log,
        stderr=subprocess.STDOUT,
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
  if wait_http_ok "$url" "$timeout"; then
    echo "[beta] ${name} ready: ${url}"
    return 0
  fi
  echo "[beta] WARN: ${name} not ready within ${timeout}s: ${url}" >&2
  return 1
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
  APP_BETA_CMD=(env CDN_DOMAIN="${CDN_DOMAIN}" "$APP_BETA" --restart)
  if [[ "$START_APP" != "1" ]]; then
    APP_BETA_CMD+=(--skip-app)
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
  if [[ -n "$MEDIA_BASE_URL" ]]; then
    APP_BETA_CMD+=(--media-base-url "$MEDIA_BASE_URL")
  fi
  if [[ -n "$GATEWAY_BASE_URL_OVERRIDE" ]]; then
    APP_BETA_CMD+=(--gateway-base-url "$GATEWAY_BASE_URL_OVERRIDE")
  fi
}

resolve_device_id_if_needed() {
  if [[ "$START_APP" != "1" || -n "$DEVICE_ID" ]]; then
    return 0
  fi
  local devices_json
  devices_json="$(python3 "$DEVICE_DISCOVERY_SCRIPT" --app-dir "$ROOT_DIR/quwoquan_app")"
  python3 - "$devices_json" <<'PY' >"$STATE_DIR/device_choices.tsv"
import json
import sys

payload = json.loads(sys.argv[1])
for device in payload.get("devices") or []:
    print(
        "\t".join(
            [
                str(device.get("id", "")).strip(),
                str(device.get("name", "")).strip(),
                str(device.get("targetPlatform", "")).strip(),
            ]
        )
    )
PY
  DEVICE_CHOICES=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    DEVICE_CHOICES+=("$line")
  done <"$STATE_DIR/device_choices.tsv"
  if [[ "${#DEVICE_CHOICES[@]}" -eq 0 ]]; then
    echo "GATE_BLOCK: no Flutter mobile device is visible for beta app launch." >&2
    exit 2
  fi
  if [[ "${#DEVICE_CHOICES[@]}" -eq 1 ]]; then
    IFS=$'\t' read -r DEVICE_ID _ <<<"${DEVICE_CHOICES[0]}"
    echo "[beta] auto selected Flutter device: ${DEVICE_CHOICES[0]}"
    return 0
  fi
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo "GATE_BLOCK: multiple Flutter devices visible; rerun with DEVICE_ID=<id> or --device-id <id>." >&2
    printf '%s\n' "${DEVICE_CHOICES[@]}" >&2
    exit 2
  fi
  echo "[beta] multiple Flutter devices visible; pick one:"
  local idx=1
  local choice
  for choice in "${DEVICE_CHOICES[@]}"; do
    IFS=$'\t' read -r id name platform <<<"$choice"
    echo "  [$idx] $name ($id, $platform)"
    idx=$((idx + 1))
  done
  local selected=""
  while [[ -z "$selected" ]]; do
    printf 'Select device [1-%d]: ' "${#DEVICE_CHOICES[@]}"
    local line=""
    IFS= read -r line || true
    if [[ "$line" =~ ^[0-9]+$ ]] && (( line >= 1 && line <= ${#DEVICE_CHOICES[@]} )); then
      local selected_index=$((line - 1))
      selected="${DEVICE_CHOICES[$selected_index]}"
      break
    fi
    echo "Invalid selection."
  done
  IFS=$'\t' read -r DEVICE_ID _ <<<"$selected"
  echo "[beta] selected Flutter device: $selected"
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
      build_app_beta_command
      start_bg app-beta "${APP_BETA_CMD[@]}"
    fi
    start_bg product-ops bash -lc "cd '$ROOT_DIR/quwoquan_service/services/product-ops-service' && APP_ENV='beta' PRODUCT_OPS_SERVICE_ADDR='127.0.0.1:${PRODUCT_OPS_PORT}' PLATFORM_OPS_BASE_URL='http://127.0.0.1:${PLATFORM_OPS_PORT}' go run ./cmd/api"
    start_bg platform-ops bash -lc "cd '$ROOT_DIR/quwoquan_service/services/platform-ops-service' && APP_ENV='beta' PLATFORM_OPS_SERVICE_ADDR='127.0.0.1:${PLATFORM_OPS_PORT}' go run ./cmd/api"
    start_bg ops-portal env VITE_PRODUCT_OPS_BASE_URL="http://127.0.0.1:${PRODUCT_OPS_PORT}" VITE_PLATFORM_OPS_BASE_URL="http://127.0.0.1:${PLATFORM_OPS_PORT}" VITE_GATEWAY_BASE_URL="http://127.0.0.1:${GATEWAY_PORT}" npm --prefix "$OPS_PORTAL_DIR" run dev -- --host 127.0.0.1 --port "${OPS_PORTAL_PORT}"
    wait_service_ok product-ops "http://127.0.0.1:${PRODUCT_OPS_PORT}/healthz" 60 || true
    wait_service_ok platform-ops "http://127.0.0.1:${PLATFORM_OPS_PORT}/healthz" 60 || true
    wait_service_ok ops-portal "http://127.0.0.1:${OPS_PORTAL_PORT}/" 60 || true
    maybe_open_ops
    status_one app-beta "http://127.0.0.1:${GATEWAY_PORT}/healthz"
    status_one product-ops "http://127.0.0.1:${PRODUCT_OPS_PORT}/healthz"
    status_one platform-ops "http://127.0.0.1:${PLATFORM_OPS_PORT}/healthz"
    status_one ops-portal "http://127.0.0.1:${OPS_PORTAL_PORT}/"
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
    status_one app-beta "http://127.0.0.1:${GATEWAY_PORT}/healthz"
    status_one product-ops "http://127.0.0.1:${PRODUCT_OPS_PORT}/healthz"
    status_one platform-ops "http://127.0.0.1:${PLATFORM_OPS_PORT}/healthz"
    status_one ops-portal "http://127.0.0.1:${OPS_PORTAL_PORT}/"
    status_one gateway "http://127.0.0.1:${GATEWAY_PORT}/healthz"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
