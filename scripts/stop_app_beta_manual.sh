#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/tmp/app_beta_manual"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
FLUTTER_DEVICE_ID="${FLUTTER_DEVICE_ID:-}"
IOS_BUNDLE_ID="${IOS_BUNDLE_ID:-com.example.quwoquanApp}"
ANDROID_PACKAGE="${ANDROID_PACKAGE:-com.quwoquan.quwoquan_app}"
CLEAN_ENV=0
PURGE_LOGS=0
TERMINATE_APP=0

BETA_MANUAL_LABEL="app-beta-manual"
BETA_MANUAL_STACK_NAME="app_beta_manual"
BETA_MANUAL_LOG_DIR="$LOG_DIR"
source "$ROOT_DIR/scripts/lib/beta_manual_lifecycle.sh"

usage() {
  cat <<EOF
Usage:
  scripts/stop_app_beta_manual.sh [options]

Options:
  --clean-env       Remove runtime pid/env state after stopping.
  --purge-logs      Remove $LOG_DIR after stopping.
  --terminate-app   Also terminate the Flutter app on --device-id when possible.
  --device-id <id>  Simulator/emulator id used with --terminate-app.
  -h, --help        Show this help.

Ports:
  assistant-service: 18087
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
  beta_manual_terminate_flutter_app "$FLUTTER_DEVICE_ID" "$IOS_BUNDLE_ID" "$ANDROID_PACKAGE"
fi

if [[ "$PURGE_LOGS" == "1" ]]; then
  rm -rf "$LOG_DIR"
fi

echo "[app-beta-manual] unified beta stack stopped."
