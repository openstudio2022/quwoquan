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
CONTENT_RELEASE_ID="${QWQ_CONTENT_RELEASE_ID:-}"
CONTENT_MANIFEST_DIGEST="${QWQ_CONTENT_MANIFEST_DIGEST:-}"
CONTENT_READINESS_RECEIPT_DIGEST="${QWQ_CONTENT_READINESS_RECEIPT_DIGEST:-}"
APP_PREFLIGHT_JSON="{}"
LAUNCH_POLICY=""

usage() {
  cat <<EOF
Usage:
  quwoquan_app/scripts/device/run_app_instance.sh --env <alpha|beta|gamma|prod> --target <target> --device-id <id> [options]

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
  alpha|beta|gamma)
    LAUNCH_POLICY="test_live"
    ;;
  prod)
    LAUNCH_POLICY="prod_release"
    ;;
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

if [[ "$TARGET_NAME" == "alpha-local" \
   || "$TARGET_NAME" == "beta-local" \
   || "$TARGET_NAME" == "gamma-local" ]]; then
  APP_PREFLIGHT_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
      app-debug-preflight --target "$TARGET_NAME" --runtime-mode test_live
  )" || {
    echo "$APP_PREFLIGHT_JSON" >&2
    echo "GATE_BLOCK: target runtime/content preflight failed for $TARGET_NAME." >&2
    exit 2
  }
  CONTENT_BINDING_EXPORTS="$(
    python3 - "$APP_PREFLIGHT_JSON" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
if payload.get("status") not in {"passed", "warning"}:
    raise SystemExit("App Debug preflight did not allow test_live")
for warning in payload.get("warnings") or []:
    print(f"[app-instance] WARN: {warning}", file=sys.stderr)
for key, field in (
    ("CONTENT_RELEASE_ID", "releaseId"),
    ("CONTENT_MANIFEST_DIGEST", "manifestDigest"),
    ("CONTENT_READINESS_RECEIPT_DIGEST", "readinessReceiptDigest"),
):
    value = str(payload.get(field) or "").strip()
    if value:
        print(f"{key}={shlex.quote(value)}")
PY
  )" || {
    echo "GATE_BLOCK: App content preflight returned an invalid receipt." >&2
    exit 2
  }
  eval "$CONTENT_BINDING_EXPORTS"
  export QWQ_APP_PREFLIGHT_JSON="$APP_PREFLIGHT_JSON"
fi

if [[ "$LAUNCH_POLICY" == "prod_release" ]]; then
  if [[ -z "$CONTENT_RELEASE_ID" \
     || ! "$CONTENT_MANIFEST_DIGEST" =~ ^sha256:[0-9a-f]{64}$ \
     || ! "$CONTENT_READINESS_RECEIPT_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "GATE_BLOCK: canonical launcher requires release-bound content identity." >&2
    exit 2
  fi
fi
export QWQ_CONTENT_RELEASE_ID="$CONTENT_RELEASE_ID"
export QWQ_CONTENT_MANIFEST_DIGEST="$CONTENT_MANIFEST_DIGEST"
export QWQ_CONTENT_READINESS_RECEIPT_DIGEST="$CONTENT_READINESS_RECEIPT_DIGEST"

if [[ "$LAUNCH_POLICY" == "test_live" ]]; then
  if ! PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/lib/public_domain_tls.py" verify \
    --target "$TARGET_NAME" >/dev/null; then
    echo "[app-instance] WARN: canonical certificate is unavailable for $TARGET_NAME; test_live continues with typed network recovery." >&2
  fi
elif [[ "$TARGET_NAME" != "prod-hosted" ]]; then
  if ! PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/lib/public_domain_tls.py" verify \
    --target "$TARGET_NAME" >/dev/null; then
    echo "GATE_BLOCK: App launch requires the canonical certificate for $TARGET_NAME." >&2
    exit 2
  fi
fi
if [[ "$TARGET_NAME" == "alpha-local" \
   || "$TARGET_NAME" == "beta-local" \
   || "$TARGET_NAME" == "gamma-local" ]]; then
  if [[ -z "${QWQ_DEVICE_TRUST_PLATFORM:-}" \
     || -z "${QWQ_DEVICE_TRUST_RECEIPT:-}" \
     || ! -f "${QWQ_DEVICE_TRUST_RECEIPT:-}" ]]; then
    echo "[app-instance] WARN: target/device system-trust receipt is unavailable; test_live continues with typed network recovery." >&2
  elif ! PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
    device-trust --target "$TARGET_NAME" \
    --platform "$QWQ_DEVICE_TRUST_PLATFORM" \
    --action verify --device "$DEVICE_ID" >/dev/null; then
    echo "[app-instance] WARN: device default trust stack cannot reach $TARGET_NAME; test_live continues with typed network recovery." >&2
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
    return 2
  }
  eval "$android_exports"
}

if ! prepare_android_reverse; then
  unset QWQ_ANDROID_LOCAL_TARGET
  unset QWQ_ANDROID_LOCAL_PORTS
  if [[ "$LAUNCH_POLICY" == "test_live" ]]; then
    echo "[app-instance] WARN: Android reverse transport is unavailable; test_live continues with typed network recovery." >&2
  else
    echo "GATE_BLOCK: Android reverse transport is required for $TARGET_NAME." >&2
    exit 2
  fi
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
  bash "$ROOT_DIR/quwoquan_app/scripts/device/run_stop_app_instance.sh" --env "$ENV_NAME" --device-id "$DEVICE_ID" --quiet || true
fi

export QWQ_RUN_DEVICE_ID="$DEVICE_ID"
export QWQ_RUN_CONSUMER_ID="app-instance-${INSTANCE_ID}-$$"
export QWQ_CONSUMER_LEASE_ACQUIRED=0
export QWQ_CONSUMER_LEASE_ID=""

release_android_consumer_lease() {
  if command -v adb >/dev/null 2>&1; then
    IFS=',' read -r -a reverse_ports <<< "${QWQ_ANDROID_LOCAL_PORTS:-}"
    for port in "${reverse_ports[@]}"; do
      [[ -z "$port" ]] && continue
      if ! adb -s "$DEVICE_ID" reverse --remove "tcp:$port" >/dev/null 2>&1; then
        echo "[app-instance] WARN: failed to remove owned adb reverse tcp:$port." >&2
      fi
    done
  fi
  if [[ "${QWQ_CONSUMER_LEASE_ACQUIRED:-0}" != "1" ]]; then
    return
  fi
  python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" consumer-lease release \
    --target "$QWQ_ANDROID_LOCAL_TARGET" \
    --device "$DEVICE_ID" \
    --consumer "$QWQ_RUN_CONSUMER_ID" >/dev/null || \
    echo "[app-instance] WARN: failed to release Android runtime consumer lease." >&2
  QWQ_CONSUMER_LEASE_ACQUIRED=0
}

if [[ -n "${QWQ_ANDROID_LOCAL_TARGET:-}" ]]; then
  trap release_android_consumer_lease EXIT
fi

if [[ -n "${QWQ_ANDROID_LOCAL_TARGET:-}" ]]; then
  if [[ -z "${QWQ_ANDROID_LOCAL_PORTS:-}" ]]; then
    if [[ "$LAUNCH_POLICY" == "test_live" ]]; then
      echo "[app-instance] WARN: Android local topology did not provide reverse ports; test_live continues with typed network recovery." >&2
      unset QWQ_ANDROID_LOCAL_TARGET
    else
      echo "GATE_BLOCK: Android local topology did not provide reverse ports." >&2
      exit 2
    fi
  else
    export ANDROID_SERIAL="$DEVICE_ID"
    LEASE_COMMAND=(
      python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json
      consumer-lease acquire
      --target "$QWQ_ANDROID_LOCAL_TARGET"
      --device "$DEVICE_ID"
      --consumer "$QWQ_RUN_CONSUMER_ID"
      --package-name com.quwoquan.quwoquan_app
      --ports "$QWQ_ANDROID_LOCAL_PORTS"
    )
    if [[ -n "$CONTENT_RELEASE_ID" ]]; then
      LEASE_COMMAND+=(
        --release-id "$CONTENT_RELEASE_ID"
        --manifest-digest "$CONTENT_MANIFEST_DIGEST"
        --readiness-receipt-digest "$CONTENT_READINESS_RECEIPT_DIGEST"
      )
    fi
    if LEASE_JSON="$("${LEASE_COMMAND[@]}")"; then
      if QWQ_CONSUMER_LEASE_ID="$(
        python3 - "$LEASE_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
lease_id = str((payload.get("lease") or {}).get("leaseId") or "")
if not lease_id:
    raise SystemExit("consumer lease response is missing leaseId")
print(lease_id)
PY
      )"; then
        export QWQ_CONSUMER_LEASE_ID
        QWQ_CONSUMER_LEASE_ACQUIRED=1
      else
        if [[ "$LAUNCH_POLICY" == "test_live" ]]; then
          echo "[app-instance] WARN: Android runtime consumer lease response is invalid; test_live continues without a lease." >&2
        else
          echo "GATE_BLOCK: Android runtime consumer lease response is invalid." >&2
          exit 2
        fi
      fi
    else
      if [[ "$LAUNCH_POLICY" == "test_live" ]]; then
        echo "[app-instance] WARN: Android runtime consumer lease is unavailable; test_live continues without a lease." >&2
      else
        echo "GATE_BLOCK: Android runtime consumer lease is unavailable." >&2
        exit 2
      fi
    fi
  fi
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
  --launch-policy "$LAUNCH_POLICY"
)
if [[ -n "$CONTENT_RELEASE_ID" ]]; then
  handoff_cmd+=(
    --content-release-id "$CONTENT_RELEASE_ID"
    --content-manifest-digest "$CONTENT_MANIFEST_DIGEST"
    --content-readiness-receipt-digest "$CONTENT_READINESS_RECEIPT_DIGEST"
  )
fi
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
if [[ "${QWQ_CONSUMER_LEASE_ACQUIRED:-0}" == "1" ]]; then
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
    "APP_DOWNLOAD_BASE_URL": handoff["appDownloadBaseUrl"],
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
if [[ "${QWQ_CONSUMER_LEASE_ACQUIRED:-0}" == "1" ]]; then
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
export QWQ_APP_LAUNCH_POLICY="$LAUNCH_POLICY"
export QWQ_LAUNCH_TARGET="$TARGET_NAME"
export QWQ_APP_BUILD_CONTEXT="runtime"
export QWQ_DART_DEFINES_DIGEST="$DART_DEFINES_DIGEST"
export QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST="$RUNTIME_CONFIG_DIGEST"
export QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST="$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
export QWQ_APP_RECOVERY_BASE_URL="$RECOVERY_BASE_URL"
export QWQ_APP_PUBLIC_WEB_URL="$PUBLIC_WEB_BASE_URL"
export QWQ_APP_DOWNLOAD_BASE_URL="$APP_DOWNLOAD_BASE_URL"
export QWQ_LAUNCH_HANDOFF_JSON="$HANDOFF_JSON"
if [[ "${QWQ_CONSUMER_LEASE_ACQUIRED:-0}" == "1" ]]; then
  LEASE_BIND_COMMAND=(
    python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json
    consumer-lease acquire
    --target "$QWQ_ANDROID_LOCAL_TARGET"
    --device "$DEVICE_ID"
    --consumer "$QWQ_RUN_CONSUMER_ID"
    --package-name com.quwoquan.quwoquan_app
    --ports "$QWQ_ANDROID_LOCAL_PORTS"
    --handoff-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  )
  if [[ -n "$CONTENT_RELEASE_ID" ]]; then
    LEASE_BIND_COMMAND+=(
      --release-id "$CONTENT_RELEASE_ID"
      --manifest-digest "$CONTENT_MANIFEST_DIGEST"
      --readiness-receipt-digest "$CONTENT_READINESS_RECEIPT_DIGEST"
    )
  fi
  if ! PYTHONDONTWRITEBYTECODE=1 "${LEASE_BIND_COMMAND[@]}" >/dev/null; then
    if [[ "$LAUNCH_POLICY" == "test_live" ]]; then
      echo "[app-instance] WARN: failed to bind the runtime consumer lease to the final handoff digest." >&2
    else
      echo "GATE_BLOCK: failed to bind the runtime consumer lease to the final handoff digest." >&2
      exit 2
    fi
  fi
fi
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
preflight = json.loads(os.environ.get("QWQ_APP_PREFLIGHT_JSON", "{}"))
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
        "appDownloadBaseUrl": defines.get("APP_DOWNLOAD_BASE_URL", ""),
        "runtimeConfigDigest": handoff["runtimeConfigDigest"],
        "dartDefinesDigest": handoff["dartDefinesDigest"],
        "preflightStatus": str(preflight.get("status") or "not_run"),
        "runtimeWarnings": list(preflight.get("warnings") or []),
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
