#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
if [[ -z "${QWQ_OBSERVABILITY_RUN_ROOT:-}" || -z "${QWQ_RUN_ROOT:-}" ]]; then
  eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_run.py" \
    --env beta --target beta-local --action down --output-root "$QWQ_OUTPUT_ROOT")"
fi
LOG_DIR="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
TLS_PROXY_DATA_VOLUME="${TLS_PROXY_DATA_VOLUME:-quwoquan_beta_local_caddy_data}"
TLS_PROXY_CONFIG_VOLUME="${TLS_PROXY_CONFIG_VOLUME:-quwoquan_beta_local_caddy_config}"
TLS_PROXY_NAME="quwoquan_beta_tls_proxy"
eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile beta-local --format shell-defaults)"
GATEWAY_PORT="${GATEWAY_PORT}"
FLUTTER_DEVICE_ID="${FLUTTER_DEVICE_ID:-}"
IOS_BUNDLE_ID="${IOS_BUNDLE_ID:-com.example.quwoquanApp}"
ANDROID_PACKAGE="${ANDROID_PACKAGE:-com.quwoquan.quwoquan_app}"
CLEAN_ENV=0
PURGE_LOGS=0
ROTATE_CA=0
TERMINATE_APP=0

BETA_MANUAL_LABEL="app-beta-manual"
BETA_MANUAL_STACK_NAME="beta-local"
BETA_MANUAL_LOG_DIR="$LOG_DIR"
BETA_MANUAL_STATE_DIR="${QWQ_OUTPUT_ROOT}/env/beta/local/beta-local/process"
BETA_MANUAL_RUNTIME_LOG_PROCESS="$ROOT_DIR/quwoquan_ops/cli/lib/runtime_log_process.py"
export BETA_MANUAL_RUNTIME_LOG_PROCESS
source "$ROOT_DIR/quwoquan_ops/cli/lib/beta_manual_lifecycle.sh"

usage() {
  cat <<EOF
Usage:
  scripts/stop_app_beta_manual.sh [options]

Options:
  --clean-env       Remove runtime pid/env state after stopping.
  --purge-logs      Remove runtime logs only; preserve the local Caddy CA.
  --rotate-ca       Explicitly remove the local Caddy CA after stopping.
  --terminate-app   Also terminate the Flutter app on --device-id when possible.
  --device-id <id>  Simulator/emulator id used with --terminate-app.
  -h, --help        Show this help.

Ports:
  assistant-service: ${ASSISTANT_PORT:-18230}
  gateway:           ${GATEWAY_PORT}
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean-env)
      CLEAN_ENV=1
      shift
      ;;
    --purge-logs)
      PURGE_LOGS=1
      CLEAN_ENV=1
      shift
      ;;
    --rotate-ca)
      ROTATE_CA=1
      shift
      ;;
    --terminate-app)
      TERMINATE_APP=1
      shift
      ;;
    --device-id)
      FLUTTER_DEVICE_ID="${2:-}"
      shift 2
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

beta_manual_init
if [[ -z "$FLUTTER_DEVICE_ID" && -f "$BETA_MANUAL_STATE_DIR/stack.env" ]]; then
  # shellcheck disable=SC1090
  source "$BETA_MANUAL_STATE_DIR/stack.env"
  FLUTTER_DEVICE_ID="${flutter_device_id:-}"
fi

beta_manual_stop_stack "$CLEAN_ENV"

if [[ "$TERMINATE_APP" == "1" ]]; then
  if [[ -n "$FLUTTER_DEVICE_ID" ]]; then
    "$ROOT_DIR/quwoquan_app/scripts/device/stop_app_instance.sh" --env beta --device-id "$FLUTTER_DEVICE_ID" --quiet || true
  fi
  beta_manual_terminate_flutter_app "$FLUTTER_DEVICE_ID" "$IOS_BUNDLE_ID" "$ANDROID_PACKAGE"
fi

if [[ "$PURGE_LOGS" == "1" ]]; then
  if [[ -d "$LOG_DIR" ]]; then
    find "$LOG_DIR" -mindepth 1 -maxdepth 1 -delete
  fi
fi

if [[ "$ROTATE_CA" == "1" ]]; then
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  elif command -v podman >/dev/null 2>&1; then
    podman rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  fi
  "$CONTAINER_RUNTIME" volume rm -f "$TLS_PROXY_DATA_VOLUME" "$TLS_PROXY_CONFIG_VOLUME" >/dev/null 2>&1 || true
  echo "[app-beta-manual] local Caddy CA rotated."
fi

echo "[app-beta-manual] unified beta stack stopped."
