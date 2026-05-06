#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"
STATE_ROOT="${APP_INSTANCE_STATE_ROOT:-$ROOT_DIR/tmp/app-instances}"

ENV_NAME=""
DEVICE_ID=""
GATEWAY_BASE_URL=""
MEDIA_BASE_URL=""
MEDIA_AVATAR_BASE_URL=""
MEDIA_IMAGE_BASE_URL=""
MEDIA_VIDEO_BASE_URL=""
MEDIA_UPLOAD_BASE_URL=""
CONTRACT_FIXTURE_PROFILE=""
CURRENT_USER_ID=""
INSTANCE_NAMESPACE="${APP_INSTANCE_NAMESPACE:-manual}"
SERVICE_MODE="${APP_INSTANCE_SERVICE_MODE:-app-only}"

usage() {
  cat <<EOF
Usage:
  scripts/start_app_instance.sh --env <alpha|beta|gamma> --device-id <id> [options]

Options:
  --gateway-base-url <url>        Override CLOUD_GATEWAY_BASE_URL.
  --media-base-url <url>          Override all MEDIA_* base URLs.
  --media-avatar-base-url <url>   Override MEDIA_AVATAR_CDN_BASE_URL only.
  --media-image-base-url <url>    Override MEDIA_IMAGE_CDN_BASE_URL only.
  --media-video-base-url <url>    Override MEDIA_VIDEO_CDN_BASE_URL only.
  --media-upload-base-url <url>   Override MEDIA_UPLOAD_BASE_URL only.
  --contract-fixture-profile <p>  Override CONTRACT_FIXTURE_PROFILE.
  --current-user-id <id>          Override APP_CURRENT_USER_ID.
  --instance-namespace <name>     Diagnostic namespace for this app instance.
  --service-mode <mode>           Diagnostic mode (default: app-only).
  -h, --help                      Show this help.

This script only starts the App instance and records runtime state under:
  $STATE_ROOT/<env>/<device-id>.json

It does not create extra beta/gamma service stacks.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_NAME="${2:-}"
      shift 2
      ;;
    --device-id)
      DEVICE_ID="${2:-}"
      shift 2
      ;;
    --gateway-base-url)
      GATEWAY_BASE_URL="${2:-}"
      shift 2
      ;;
    --media-base-url)
      MEDIA_BASE_URL="${2:-}"
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
    --contract-fixture-profile)
      CONTRACT_FIXTURE_PROFILE="${2:-}"
      shift 2
      ;;
    --current-user-id)
      CURRENT_USER_ID="${2:-}"
      shift 2
      ;;
    --instance-namespace)
      INSTANCE_NAMESPACE="${2:-}"
      shift 2
      ;;
    --service-mode)
      SERVICE_MODE="${2:-}"
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

case "$ENV_NAME" in
  alpha|beta|gamma) ;;
  *)
    echo "FAIL: --env must be one of alpha|beta|gamma" >&2
    exit 2
    ;;
esac

if [[ -z "$DEVICE_ID" ]]; then
  echo "FAIL: --device-id is required to avoid interactive Flutter device selection." >&2
  exit 2
fi

sanitize_device_id() {
  python3 - "$1" <<'PY'
import re
import sys
print(re.sub(r"[^A-Za-z0-9._-]+", "_", sys.argv[1]).strip("_") or "device")
PY
}

SANITIZED_DEVICE_ID="$(sanitize_device_id "$DEVICE_ID")"
STATE_DIR="$STATE_ROOT/$ENV_NAME"
STATE_FILE="$STATE_DIR/$SANITIZED_DEVICE_ID.json"
INSTANCE_ID="${ENV_NAME}-${SANITIZED_DEVICE_ID}"
mkdir -p "$STATE_DIR"

if [[ -f "$STATE_FILE" ]]; then
  bash "$ROOT_DIR/scripts/stop_app_instance.sh" --env "$ENV_NAME" --device-id "$DEVICE_ID" --quiet || true
fi

define_cmd=(
  python3 "$ROOT_DIR/scripts/print_app_env_dart_defines.py"
  --env "$ENV_NAME"
  --format json
  --app-instance-id "$INSTANCE_ID"
  --app-instance-namespace "$INSTANCE_NAMESPACE"
)
if [[ -n "$GATEWAY_BASE_URL" ]]; then
  define_cmd+=(--gateway-base-url "$GATEWAY_BASE_URL")
fi
if [[ -n "$MEDIA_BASE_URL" ]]; then
  define_cmd+=(--media-base-url "$MEDIA_BASE_URL")
fi
if [[ -n "$MEDIA_AVATAR_BASE_URL" ]]; then
  define_cmd+=(--media-avatar-base-url "$MEDIA_AVATAR_BASE_URL")
fi
if [[ -n "$MEDIA_IMAGE_BASE_URL" ]]; then
  define_cmd+=(--media-image-base-url "$MEDIA_IMAGE_BASE_URL")
fi
if [[ -n "$MEDIA_VIDEO_BASE_URL" ]]; then
  define_cmd+=(--media-video-base-url "$MEDIA_VIDEO_BASE_URL")
fi
if [[ -n "$MEDIA_UPLOAD_BASE_URL" ]]; then
  define_cmd+=(--media-upload-base-url "$MEDIA_UPLOAD_BASE_URL")
fi
if [[ -n "$CONTRACT_FIXTURE_PROFILE" ]]; then
  define_cmd+=(--contract-fixture-profile "$CONTRACT_FIXTURE_PROFILE")
fi
if [[ -n "$CURRENT_USER_ID" ]]; then
  define_cmd+=(--current-user-id "$CURRENT_USER_ID")
fi

DEFINES_JSON="$("${define_cmd[@]}")"

echo "[app-instance] env=$ENV_NAME device=$DEVICE_ID namespace=$INSTANCE_NAMESPACE mode=$SERVICE_MODE"

python3 - "$APP_DIR" "$STATE_FILE" "$ENV_NAME" "$DEVICE_ID" "$INSTANCE_ID" "$INSTANCE_NAMESPACE" "$SERVICE_MODE" "$DEFINES_JSON" <<'PY'
import datetime as dt
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

app_dir, state_file, env_name, device_id, instance_id, instance_namespace, service_mode, defines_json = sys.argv[1:9]
defines = json.loads(defines_json or "{}")
state_path = Path(state_file)
state_path.parent.mkdir(parents=True, exist_ok=True)

command = ["flutter", "run", "-d", device_id]
for key, value in defines.items():
    command.append(f"--dart-define={key}={value}")

child: subprocess.Popen[bytes] | None = None


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def cleanup_state() -> None:
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass


def forward_signal(signum: int, _frame: object) -> None:
    if child is None or child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signum)
    except ProcessLookupError:
        return


signal.signal(signal.SIGINT, forward_signal)
signal.signal(signal.SIGTERM, forward_signal)
signal.signal(signal.SIGHUP, forward_signal)

try:
    child = subprocess.Popen(
        command,
        cwd=app_dir,
        start_new_session=True,
    )
    payload = {
        "schemaVersion": 1,
        "env": env_name,
        "deviceId": device_id,
        "instanceId": instance_id,
        "instanceNamespace": instance_namespace,
        "serviceMode": service_mode,
        "pid": child.pid,
        "pgid": os.getpgid(child.pid),
        "startedAt": utc_now(),
        "gatewayBaseUrl": defines.get("CLOUD_GATEWAY_BASE_URL", ""),
        "command": command,
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(child.wait())
finally:
    cleanup_state()
PY
