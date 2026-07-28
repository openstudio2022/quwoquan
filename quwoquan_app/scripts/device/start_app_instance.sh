#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
STATE_ROOT="${APP_INSTANCE_STATE_ROOT:-$QWQ_OUTPUT_ROOT/env/repo/local/app-instances/process}"

ENV_NAME=""
TARGET_NAME=""
DEVICE_ID=""
GATEWAY_BASE_URL=""
LEGAL_BASE_URL=""
MEDIA_AVATAR_BASE_URL=""
MEDIA_IMAGE_BASE_URL=""
MEDIA_VIDEO_BASE_URL=""
MEDIA_UPLOAD_BASE_URL=""
CURRENT_USER_ID=""
INSTANCE_NAMESPACE="${APP_INSTANCE_NAMESPACE:-manual}"
SERVICE_MODE="${APP_INSTANCE_SERVICE_MODE:-app-only}"
ROLLOUT_MODE="${APP_ROLLOUT_MODE:-}"

usage() {
  cat <<EOF
Usage:
  quwoquan_app/scripts/device/start_app_instance.sh --env <alpha|beta|gamma|prod> --target <target> --device-id <id> [options]

Options:
  --target <target>                alpha-local|beta-local|gamma-local|prod-sim|prod-hosted.
  --gateway-base-url <url>        Override CLOUD_GATEWAY_BASE_URL.
  --legal-base-url <url>          Override APP_LEGAL_BASE_URL.
  --media-avatar-base-url <url>   Override MEDIA_AVATAR_CDN_BASE_URL only.
  --media-image-base-url <url>    Override MEDIA_IMAGE_CDN_BASE_URL only.
  --media-video-base-url <url>    Override MEDIA_VIDEO_CDN_BASE_URL only.
  --media-upload-base-url <url>   Override MEDIA_UPLOAD_BASE_URL only.
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
    --target)
      TARGET_NAME="${2:-}"
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

case "$ENV_NAME:$TARGET_NAME" in
  alpha:alpha-local|beta:beta-local|gamma:gamma-local|prod:prod-sim|prod:prod-hosted) ;;
  *)
    echo "FAIL: --target must explicitly match --env (prod accepts prod-sim or prod-hosted)." >&2
    exit 2
    ;;
esac

if [[ -z "$DEVICE_ID" ]]; then
  echo "FAIL: --device-id is required to avoid interactive Flutter device selection." >&2
  exit 2
fi

if [[ "$TARGET_NAME" != "prod-hosted" ]]; then
  if ! PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/lib/public_domain_tls.py" verify \
    --target "$TARGET_NAME" >/dev/null; then
    echo "GATE_BLOCK: local App launch requires a valid DNS-01 public certificate for $TARGET_NAME." >&2
    exit 2
  fi
fi

prepare_android_reverse() {
  local android_exports
  android_exports="$(
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - "$TARGET_NAME" "$DEVICE_ID" <<'PY'
import hashlib
import shlex
import sys

from quwoquan_ops.cli.lib.dev_up import (
    detect_device_kind,
    enable_android_adb_reverse,
    find_device,
    load_environment_topology,
)

target, device_id = sys.argv[1:]
if target == "prod-hosted":
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
ports = enable_android_adb_reverse(device_id, target, topology=topology)
port_list = ",".join(str(port) for port in ports)
print("export QWQ_ANDROID_LOCAL_PORTS=" + shlex.quote(
    port_list
))
print("export QWQ_ANDROID_REVERSE_EXPECTED_PORTS=" + shlex.quote(
    port_list
))
print("export QWQ_ANDROID_REVERSE_ACTUAL_PORTS=" + shlex.quote(port_list))
print("export QWQ_ANDROID_REVERSE_RECEIPT_DIGEST=" + shlex.quote(
    "sha256:" + hashlib.sha256(
        f"{target}\0{device_id}\0{port_list}".encode("utf-8")
    ).hexdigest()
))
print("export QWQ_ANDROID_LOCAL_TARGET=" + shlex.quote(target))
PY
  )" || {
    echo "GATE_BLOCK: failed to resolve Android Remote topology." >&2
    return 2
  }
  eval "$android_exports"
}

prepare_android_reverse

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

export QWQ_RUN_DEVICE_ID="$DEVICE_ID"
export QWQ_RUN_CONSUMER_ID="app-instance-${INSTANCE_ID}-$$"
export QWQ_CONSUMER_LEASE_ACQUIRED=0
export QWQ_CONSUMER_LEASE_ID=""

release_android_consumer_lease() {
  if [[ "${QWQ_CONSUMER_LEASE_ACQUIRED:-0}" != "1" ]]; then
    return
  fi
  if command -v adb >/dev/null 2>&1; then
    IFS=',' read -r -a reverse_ports <<< "${QWQ_ANDROID_LOCAL_PORTS:-}"
    for port in "${reverse_ports[@]}"; do
      [[ -z "$port" ]] && continue
      if ! adb -s "$DEVICE_ID" reverse --remove "tcp:$port" >/dev/null 2>&1; then
        echo "[app-instance] WARN: failed to remove owned adb reverse tcp:$port." >&2
      fi
    done
  fi
  python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" consumer-lease release \
    --target "$QWQ_ANDROID_LOCAL_TARGET" \
    --device "$DEVICE_ID" \
    --consumer "$QWQ_RUN_CONSUMER_ID" >/dev/null || \
    echo "[app-instance] WARN: failed to release Android runtime consumer lease." >&2
  QWQ_CONSUMER_LEASE_ACQUIRED=0
}

if [[ -n "${QWQ_ANDROID_LOCAL_TARGET:-}" ]]; then
  if [[ -z "${QWQ_ANDROID_LOCAL_PORTS:-}" ]]; then
    echo "GATE_BLOCK: Android local topology did not provide reverse ports." >&2
    exit 2
  fi
  export ANDROID_SERIAL="$DEVICE_ID"
  LEASE_JSON="$(
    python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
      consumer-lease acquire \
      --target "$QWQ_ANDROID_LOCAL_TARGET" \
      --device "$DEVICE_ID" \
      --consumer "$QWQ_RUN_CONSUMER_ID" \
      --package-name com.quwoquan.quwoquan_app \
      --ports "$QWQ_ANDROID_LOCAL_PORTS"
  )"
  QWQ_CONSUMER_LEASE_ID="$(
    python3 - "$LEASE_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
lease_id = str((payload.get("lease") or {}).get("leaseId") or "")
if not lease_id:
    raise SystemExit("consumer lease response is missing leaseId")
print(lease_id)
PY
  )"
  export QWQ_CONSUMER_LEASE_ID
  QWQ_CONSUMER_LEASE_ACQUIRED=1
  trap release_android_consumer_lease EXIT
elif [[ "$TARGET_NAME" == "prod-hosted" ]] && command -v adb >/dev/null 2>&1 && \
  adb -s "$DEVICE_ID" get-state >/dev/null 2>&1; then
  echo "GATE_BLOCK: Android prod Flutter debug launch is unsupported; verify a signed release APK/AAB." >&2
  exit 2
fi

handoff_cmd=(
  python3 "$ROOT_DIR/quwoquan_app/scripts/device/build_launcher_handoff.py"
  --env "$ENV_NAME"
  --target "$TARGET_NAME"
  --app-instance-id "$INSTANCE_ID"
  --app-instance-namespace "$INSTANCE_NAMESPACE"
  --launch-mode canonical_launcher
)
if [[ -n "$GATEWAY_BASE_URL" ]]; then
  handoff_cmd+=(--gateway-base-url "$GATEWAY_BASE_URL")
fi
if [[ -n "$LEGAL_BASE_URL" ]]; then
  handoff_cmd+=(--legal-base-url "$LEGAL_BASE_URL")
fi
if [[ -n "$MEDIA_AVATAR_BASE_URL" ]]; then
  handoff_cmd+=(--media-avatar-base-url "$MEDIA_AVATAR_BASE_URL")
fi
if [[ -n "$MEDIA_IMAGE_BASE_URL" ]]; then
  handoff_cmd+=(--media-image-base-url "$MEDIA_IMAGE_BASE_URL")
fi
if [[ -n "$MEDIA_VIDEO_BASE_URL" ]]; then
  handoff_cmd+=(--media-video-base-url "$MEDIA_VIDEO_BASE_URL")
fi
if [[ -n "$MEDIA_UPLOAD_BASE_URL" ]]; then
  handoff_cmd+=(--media-upload-base-url "$MEDIA_UPLOAD_BASE_URL")
fi
if [[ -n "$CURRENT_USER_ID" ]]; then
  handoff_cmd+=(--current-user-id "$CURRENT_USER_ID")
fi
if [[ -n "$ROLLOUT_MODE" ]]; then
  handoff_cmd+=(--rollout-mode "$ROLLOUT_MODE")
fi
if [[ -n "${QWQ_ANDROID_LOCAL_TARGET:-}" ]]; then
  handoff_cmd+=(
    --transport-required
    --reverse-expected-ports "$QWQ_ANDROID_REVERSE_EXPECTED_PORTS"
    --reverse-actual-ports "$QWQ_ANDROID_REVERSE_ACTUAL_PORTS"
    --reverse-receipt-digest "$QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"
    --consumer-lease-id "$QWQ_CONSUMER_LEASE_ID"
  )
fi

HANDOFF_JSON="$("${handoff_cmd[@]}")"
HANDOFF_EXPORTS="$(
  python3 - "$HANDOFF_JSON" <<'PY'
import json
import shlex
import sys

handoff = json.loads(sys.argv[1])
values = {
    "DEFINES_JSON": json.dumps(
        handoff["dartDefines"],
        ensure_ascii=False,
        separators=(",", ":"),
    ),
    "ENTRYPOINT": handoff["entrypoint"],
    "DART_DEFINES_DIGEST": handoff["dartDefinesDigest"],
    "RUNTIME_CONFIG_DIGEST": handoff["runtimeConfigDigest"],
    "EFFECTIVE_LAUNCH_MANIFEST_DIGEST": handoff[
        "effectiveLaunchManifestDigest"
    ],
    "EFFECTIVE_LAUNCH_MANIFEST_JSON": json.dumps(
        handoff["effectiveLaunchManifest"],
        ensure_ascii=False,
        separators=(",", ":"),
    ),
    "RECOVERY_BASE_URL": handoff["recoveryBaseUrl"],
    "PUBLIC_WEB_BASE_URL": handoff["publicWebBaseUrl"],
}
for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)" || {
  echo "GATE_BLOCK: failed to parse launcher handoff." >&2
  exit 2
}
eval "$HANDOFF_EXPORTS"
verify_handoff_cmd=(
  python3 "$ROOT_DIR/quwoquan_app/scripts/device/verify_flutter_run_defines.py"
  --env "$ENV_NAME"
  --target "$TARGET_NAME"
  --entrypoint "$ENTRYPOINT"
  --defines-digest "$DART_DEFINES_DIGEST"
  --runtime-config-digest "$RUNTIME_CONFIG_DIGEST"
  --effective-launch-manifest-json "$EFFECTIVE_LAUNCH_MANIFEST_JSON"
  --effective-launch-manifest-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  --defines-json "$DEFINES_JSON"
)
if [[ -n "${QWQ_ANDROID_LOCAL_TARGET:-}" ]]; then
  verify_handoff_cmd+=(
    --transport-required
    --reverse-expected-ports "$QWQ_ANDROID_REVERSE_EXPECTED_PORTS"
    --reverse-actual-ports "$QWQ_ANDROID_REVERSE_ACTUAL_PORTS"
    --reverse-receipt-digest "$QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"
    --consumer-lease-id "$QWQ_CONSUMER_LEASE_ID"
  )
fi
"${verify_handoff_cmd[@]}"
export QWQ_APP_RUNTIME_ENV="$ENV_NAME"
export QWQ_APP_LAUNCH_MODE="canonical_launcher"
export QWQ_LAUNCH_TARGET="$TARGET_NAME"
export QWQ_APP_BUILD_CONTEXT="runtime"
export QWQ_DART_DEFINES_DIGEST="$DART_DEFINES_DIGEST"
export QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST="$RUNTIME_CONFIG_DIGEST"
export QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST="$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
export QWQ_APP_RECOVERY_BASE_URL="$RECOVERY_BASE_URL"
export QWQ_APP_PUBLIC_WEB_URL="$PUBLIC_WEB_BASE_URL"
export QWQ_LAUNCH_HANDOFF_JSON="$HANDOFF_JSON"
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
app_dir = Path(app_dir)
defines = json.loads(defines_json or "{}")
handoff = json.loads(os.environ["QWQ_LAUNCH_HANDOFF_JSON"])
state_path = Path(state_file)
state_path.parent.mkdir(parents=True, exist_ok=True)

entrypoint = str(handoff["entrypoint"])
command = ["flutter", "run", "--target", entrypoint, "-d", device_id]
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
        cwd=str(app_dir),
        stdin=terminal_fd,
        start_new_session=not preserve_terminal,
    )
    payload = {
        "schema": "app-instance-state",
        "env": env_name,
        "target": handoff["target"],
        "deviceId": device_id,
        "instanceId": instance_id,
        "instanceNamespace": instance_namespace,
        "serviceMode": service_mode,
        "rolloutMode": rollout_mode,
        "entrypoint": entrypoint,
        "pid": child.pid,
        "pgid": os.getpgid(child.pid),
        "startedAt": utc_now(),
        "gatewayBaseUrl": defines.get("CLOUD_GATEWAY_BASE_URL", ""),
        "legalBaseUrl": defines.get("APP_LEGAL_BASE_URL", ""),
        "publicWebBaseUrl": defines.get("PUBLIC_WEB_BASE_URL", ""),
        "runtimeConfigDigest": handoff["runtimeConfigDigest"],
        "dartDefinesDigest": handoff["dartDefinesDigest"],
        "recoveryBaseUrl": handoff["recoveryBaseUrl"],
        "dartDefines": defines,
        "androidLocalTarget": os.environ.get("QWQ_ANDROID_LOCAL_TARGET", ""),
        "androidReversePorts": os.environ.get(
            "QWQ_ANDROID_REVERSE_EXPECTED_PORTS", ""
        ),
        "androidReverseActualPorts": os.environ.get(
            "QWQ_ANDROID_REVERSE_ACTUAL_PORTS", ""
        ),
        "androidReverseReceiptDigest": os.environ.get(
            "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST", ""
        ),
        "consumerLeaseId": os.environ.get("QWQ_CONSUMER_LEASE_ID", ""),
        "command": command,
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(child.wait())
finally:
    cleanup_state()
    if terminal_fd is not None:
        os.close(terminal_fd)
PY
