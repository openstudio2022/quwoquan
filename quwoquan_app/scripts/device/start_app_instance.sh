#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
STATE_ROOT="${APP_INSTANCE_STATE_ROOT:-$QWQ_OUTPUT_ROOT/env/repo/local/app-instances/process}"

ENV_NAME=""
DEVICE_ID=""
GATEWAY_BASE_URL=""
LEGAL_BASE_URL=""
MEDIA_AVATAR_BASE_URL=""
MEDIA_IMAGE_BASE_URL=""
MEDIA_VIDEO_BASE_URL=""
MEDIA_UPLOAD_BASE_URL=""
CONTRACT_FIXTURE_PROFILE=""
CURRENT_USER_ID=""
INSTANCE_NAMESPACE="${APP_INSTANCE_NAMESPACE:-manual}"
SERVICE_MODE="${APP_INSTANCE_SERVICE_MODE:-app-only}"
ROLLOUT_MODE="${APP_ROLLOUT_MODE:-}"

usage() {
  cat <<EOF
Usage:
  quwoquan_app/scripts/device/start_app_instance.sh --env <alpha|beta|gamma|prod> --device-id <id> [options]

Options:
  --gateway-base-url <url>        Override CLOUD_GATEWAY_BASE_URL.
  --legal-base-url <url>          Override APP_LEGAL_BASE_URL.
  --media-avatar-base-url <url>   Override MEDIA_AVATAR_CDN_BASE_URL only.
  --media-image-base-url <url>    Override MEDIA_IMAGE_CDN_BASE_URL only.
  --media-video-base-url <url>    Override MEDIA_VIDEO_CDN_BASE_URL only.
  --media-upload-base-url <url>   Override MEDIA_UPLOAD_BASE_URL only.
  --contract-fixture-profile <p>  Override CONTRACT_FIXTURE_PROFILE.
  --current-user-id <id>          Override APP_CURRENT_USER_ID.
  --instance-namespace <name>     Diagnostic namespace for this app instance.
  --service-mode <mode>           Diagnostic mode (default: app-only).
  --rollout-mode <mode>           Prod rollout diagnostic mode: gray-initial|carry-on|full.
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
    --legal-base-url)
      LEGAL_BASE_URL="${2:-}"
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
    --rollout-mode)
      ROLLOUT_MODE="${2:-}"
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
  alpha|beta|gamma|prod) ;;
  *)
    echo "FAIL: --env must be one of alpha|beta|gamma|prod" >&2
    exit 2
    ;;
esac

if [[ -z "$DEVICE_ID" ]]; then
  echo "FAIL: --device-id is required to avoid interactive Flutter device selection." >&2
  exit 2
fi

install_requested_local_simulator_ca() {
  local target=""
  case "$ENV_NAME" in
    alpha) target="alpha-local" ;;
    beta) target="beta-local" ;;
    gamma) target="gamma-local" ;;
    prod)
      # `prod` may point to prod-hosted. Only the local prod-sim authority has
      # a Simulator root CA to install.
      if [[ "$GATEWAY_BASE_URL" == *".quwoquan-env.test"* ]]; then
        target="prod-sim"
      fi
      ;;
  esac
  if [[ -n "$target" && -z "${QWQ_IOS_SIMULATOR_UDID:-}" ]] && \
    python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_target_tls.py" \
      is-ios-simulator \
      --device-id "$DEVICE_ID" >/dev/null; then
    export QWQ_IOS_SIMULATOR_UDID="$DEVICE_ID"
  fi
  if [[ -z "$target" || -z "${QWQ_IOS_SIMULATOR_UDID:-}" ]]; then
    return 0
  fi
  python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_target_tls.py" \
    install-ios-simulator-ca \
    --target "$target" \
    --simulator-udid "$QWQ_IOS_SIMULATOR_UDID"
}

prepare_android_local_tls() {
  eval "$(
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - "$ENV_NAME" "$DEVICE_ID" "$GATEWAY_BASE_URL" <<'PY'
import shlex
import sys

from quwoquan_ops.cli.lib.dev_up import (
    detect_device_kind,
    enable_android_adb_reverse,
    find_device,
    load_environment_topology,
    local_target_android_debug_ca_cert,
)

env_name, device_id, gateway_base_url = sys.argv[1:]
target_by_env = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
}
target = target_by_env.get(env_name, "")
if env_name == "prod" and ".quwoquan-env.test" in gateway_base_url:
    target = "prod-sim"
if not target:
    raise SystemExit(0)

device = find_device(device_id, include_desktop=False) or {}
device_kind = detect_device_kind(
    device_id,
    target_platform=str(device.get("targetPlatform", "")),
    emulator=bool(device.get("emulator", False)) if device else None,
)
if not device_kind.startswith("android"):
    raise SystemExit(0)

topology = load_environment_topology()
enable_android_adb_reverse(device_id, target, topology=topology)
print("export QWQ_ANDROID_LOCAL_ENV_CA_PATH=" + shlex.quote(
    str(local_target_android_debug_ca_cert(target))
))
print("export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1")
PY
  )"
}

prepare_android_local_tls
install_requested_local_simulator_ca

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
  bash "$ROOT_DIR/quwoquan_app/scripts/device/stop_app_instance.sh" --env "$ENV_NAME" --device-id "$DEVICE_ID" --quiet || true
fi

define_cmd=(
  python3 "$ROOT_DIR/quwoquan_app/scripts/env/print_app_env_dart_defines.py"
  --env "$ENV_NAME"
  --format json
  --app-instance-id "$INSTANCE_ID"
  --app-instance-namespace "$INSTANCE_NAMESPACE"
  --launch-mode canonical_launcher
)
if [[ -n "$GATEWAY_BASE_URL" ]]; then
  define_cmd+=(--gateway-base-url "$GATEWAY_BASE_URL")
fi
if [[ -n "$LEGAL_BASE_URL" ]]; then
  define_cmd+=(--legal-base-url "$LEGAL_BASE_URL")
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
if [[ -n "$ROLLOUT_MODE" ]]; then
  define_cmd+=(--rollout-mode "$ROLLOUT_MODE")
fi

DEFINES_JSON="$("${define_cmd[@]}")"
python3 "$ROOT_DIR/quwoquan_app/scripts/device/verify_flutter_run_defines.py" \
  --env "$ENV_NAME" \
  --defines-json "$DEFINES_JSON"
export QWQ_APP_RUNTIME_ENV="$ENV_NAME"
export QWQ_APP_LAUNCH_MODE="canonical_launcher"
if [[ -t 0 && -e /dev/tty ]]; then
  export QWQ_APP_INSTANCE_PRESERVE_TTY="${QWQ_APP_INSTANCE_PRESERVE_TTY:-1}"
fi

echo "[app-instance] env=$ENV_NAME device=$DEVICE_ID namespace=$INSTANCE_NAMESPACE mode=$SERVICE_MODE"

python3 - "$APP_DIR" "$STATE_FILE" "$ENV_NAME" "$DEVICE_ID" "$INSTANCE_ID" "$INSTANCE_NAMESPACE" "$SERVICE_MODE" "$ROLLOUT_MODE" "$DEFINES_JSON" <<'PY'
import datetime as dt
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

app_dir, state_file, env_name, device_id, instance_id, instance_namespace, service_mode, rollout_mode, defines_json = sys.argv[1:10]
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
    preserve_terminal = os.environ.get("QWQ_APP_INSTANCE_PRESERVE_TTY") == "1"
    terminal_fd = None
    if preserve_terminal:
        try:
            terminal_fd = os.open("/dev/tty", os.O_RDWR)
        except OSError:
            terminal_fd = None
    child = subprocess.Popen(
        command,
        cwd=app_dir,
        stdin=terminal_fd,
        start_new_session=not preserve_terminal,
    )
    payload = {
        "schema": "app-instance-state",
        "env": env_name,
        "deviceId": device_id,
        "instanceId": instance_id,
        "instanceNamespace": instance_namespace,
        "serviceMode": service_mode,
        "rolloutMode": rollout_mode,
        "pid": child.pid,
        "pgid": os.getpgid(child.pid),
        "startedAt": utc_now(),
        "gatewayBaseUrl": defines.get("CLOUD_GATEWAY_BASE_URL", ""),
        "legalBaseUrl": defines.get("APP_LEGAL_BASE_URL", ""),
        "command": command,
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(child.wait())
finally:
    cleanup_state()
    if terminal_fd is not None:
        os.close(terminal_fd)
PY
