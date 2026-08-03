#!/usr/bin/env bash
# 使用 env-package-backed Remote 启动入口，避免裸跑漏掉 runtime/release 合同。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
REQUESTED_ENVIRONMENT="${QWQ_ENVIRONMENT:-}"
FLUTTER_ARGUMENTS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      if [[ -z "${2:-}" ]]; then
        echo "[run] GATE_BLOCK: --env requires alpha|beta|gamma." >&2
        exit 2
      fi
      if [[ -n "$REQUESTED_ENVIRONMENT" && "$REQUESTED_ENVIRONMENT" != "$2" ]]; then
        echo "[run] GATE_BLOCK: --env conflicts with QWQ_ENVIRONMENT." >&2
        exit 2
      fi
      REQUESTED_ENVIRONMENT="$2"
      shift 2
      ;;
    --env=*)
      value="${1#*=}"
      if [[ -n "$REQUESTED_ENVIRONMENT" && "$REQUESTED_ENVIRONMENT" != "$value" ]]; then
        echo "[run] GATE_BLOCK: --env conflicts with QWQ_ENVIRONMENT." >&2
        exit 2
      fi
      REQUESTED_ENVIRONMENT="$value"
      shift
      ;;
    *)
      FLUTTER_ARGUMENTS+=("$1")
      shift
      ;;
  esac
done
set -- "${FLUTTER_ARGUMENTS[@]}"
export QWQ_ENVIRONMENT="${REQUESTED_ENVIRONMENT:-alpha}"
export QWQ_APP_RUNTIME_ENV="$QWQ_ENVIRONMENT"
case "$QWQ_APP_RUNTIME_ENV" in
  alpha|beta|gamma) ;;
  *)
    echo "[run] GATE_BLOCK: QWQ_ENVIRONMENT must be alpha|beta|gamma." >&2
    exit 2
    ;;
esac
export QWQ_LAUNCH_TARGET="${QWQ_APP_RUNTIME_ENV}-local"
export QWQ_APP_BUILD_CONTEXT=runtime

cd "$APP_DIR"

echo "[run] verifying local Flutter package resolution..."
if ! flutter pub get --offline; then
  echo "[run] FAIL: offline Flutter dependency resolution failed."
  echo "[run] This repo forbids implicit build-time network fetches. Run an explicit dependency sync only when intentionally changing third-party packages."
  exit 1
fi

PODFILE_LOCK="$APP_DIR/ios/Podfile.lock"
PODS_MANIFEST_LOCK="$APP_DIR/ios/Pods/Manifest.lock"
if [[ ! -f "$PODS_MANIFEST_LOCK" ]]; then
  echo "[run] FAIL: missing $PODS_MANIFEST_LOCK."
  echo "[run] iOS dependencies must be pre-vendored locally; do not rely on implicit CocoaPods downloads at launch time."
  exit 1
fi

if ! cmp -s "$PODFILE_LOCK" "$PODS_MANIFEST_LOCK"; then
  echo "[run] FAIL: CocoaPods lock drift detected between Podfile.lock and Pods/Manifest.lock."
  echo "[run] Resolve pod changes explicitly before launching; alpha startup must not repair dependencies over the network."
  exit 1
fi

parse_flutter_device_id() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -d|--device-id)
        echo "${2:-}"
        return 0
        ;;
      --device-id=*)
        echo "${1#*=}"
        return 0
        ;;
    esac
    shift
  done
  return 0
}

for argument in "$@"; do
  case "$argument" in
    -t|--target|--target=*)
      echo "[run] GATE_BLOCK: select alpha|beta|gamma with QWQ_ENVIRONMENT; raw Flutter target overrides are forbidden."
      exit 2
      ;;
  esac
done

export QWQ_RUN_DEVICE_ID="$(parse_flutter_device_id "$@")"
DEVICE_ID="$QWQ_RUN_DEVICE_ID"

if [[ -z "$DEVICE_ID" ]]; then
  echo "[run] GATE_BLOCK: pass -d/--device-id so runtime ports and the consumer lease bind to one device."
  exit 2
fi

echo "[run] validating full Debug runtime for $QWQ_LAUNCH_TARGET..."
if ! APP_CONTENT_PREFLIGHT_JSON="$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
    app-debug-preflight --target "$QWQ_LAUNCH_TARGET"
)"; then
  echo "$APP_CONTENT_PREFLIGHT_JSON" >&2
  echo "[run] GATE_BLOCK: target runtime or SMS Provider is not ready; fix the first typed blocker above before flutter run." >&2
  exit 2
fi
APP_CONTENT_EXPORTS="$(
  python3 - "$APP_CONTENT_PREFLIGHT_JSON" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
if payload.get("status") != "passed":
    raise SystemExit("App Debug preflight did not pass")
for key, field in (
    ("QWQ_CONTENT_RELEASE_ID", "releaseId"),
    ("QWQ_CONTENT_MANIFEST_DIGEST", "manifestDigest"),
    ("QWQ_CONTENT_READINESS_RECEIPT_DIGEST", "readinessReceiptDigest"),
):
    value = str(payload.get(field) or "").strip()
    if not value:
        raise SystemExit(f"App content preflight is missing {field}")
    print(f"export {key}={shlex.quote(value)}")
PY
)" || {
  echo "[run] GATE_BLOCK: App content preflight returned an invalid receipt." >&2
  exit 2
}
eval "$APP_CONTENT_EXPORTS"

ANDROID_LOCAL_GATEWAY_BASE_URL=""
ANDROID_LOCAL_LEGAL_BASE_URL=""
ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL=""
ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL=""
ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL=""
ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL=""
QWQ_ANDROID_LOCAL_PORTS=""
export QWQ_RUN_CONSUMER_ID="flutter-run-$$"
export QWQ_CONSUMER_LEASE_ACQUIRED=0
export QWQ_CONSUMER_LEASE_ID=""
export QWQ_ANDROID_REVERSE_OWNED_PORTS=""

release_consumer_lease() {
  if command -v adb >/dev/null 2>&1 \
    && [[ -n "$QWQ_ANDROID_REVERSE_OWNED_PORTS" ]]; then
    IFS=',' read -r -a reverse_ports <<< "$QWQ_ANDROID_REVERSE_OWNED_PORTS"
    for port in "${reverse_ports[@]}"; do
      [[ -z "$port" ]] && continue
      if ! adb -s "$DEVICE_ID" reverse --remove "tcp:$port" >/dev/null 2>&1; then
        echo "[run] WARN: failed to remove owned adb reverse tcp:$port."
      fi
    done
  fi
  if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" != "1" ]]; then
    return
  fi
  python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" consumer-lease release \
    --target "$QWQ_LAUNCH_TARGET" \
    --device "$DEVICE_ID" \
    --consumer "$QWQ_RUN_CONSUMER_ID" >/dev/null || \
    echo "[run] WARN: failed to release runtime consumer lease."
  QWQ_CONSUMER_LEASE_ACQUIRED=0
}

trap release_consumer_lease EXIT

if [[ -n "$DEVICE_ID" ]]; then
  DEVICE_EXPORTS="$(
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - \
      "$DEVICE_ID" "$QWQ_APP_RUNTIME_ENV" "$QWQ_LAUNCH_TARGET" <<'PY'
import hashlib
import re
import shlex
import subprocess
import sys

from quwoquan_ops.cli.lib.dev_up import (
    detect_device_kind,
    enable_android_adb_reverse,
    find_device,
    load_environment_topology,
    resolve_app_endpoint_overrides,
)

device_id = sys.argv[1].strip()
environment = sys.argv[2].strip()
target = sys.argv[3].strip()
device = find_device(device_id, include_desktop=False) or {}
device_kind = detect_device_kind(
    device_id,
    target_platform=str(device.get("targetPlatform", "")),
    emulator=bool(device.get("emulator", False)) if device else None,
)
print(f"export QWQ_RUN_DEVICE_KIND={shlex.quote(device_kind)}")
if device_kind.startswith("android"):
    topology = load_environment_topology()
    overrides = resolve_app_endpoint_overrides(environment, device_kind, topology=topology)
    before = subprocess.run(
        ["adb", "-s", device_id, "reverse", "--list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if before.returncode != 0:
        raise SystemExit("unable to read existing adb reverse mappings")
    preexisting_ports = {
        int(match.group(1))
        for match in re.finditer(r"tcp:(\d+)\s+tcp:\d+", before.stdout)
    }
    ports = enable_android_adb_reverse(device_id, target, topology=topology)
    port_list = ",".join(str(port) for port in ports)
    owned_port_list = ",".join(
        str(port) for port in ports if int(port) not in preexisting_ports
    )
    print("export QWQ_ANDROID_LOCAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_EXPECTED_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_ACTUAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_OWNED_PORTS=" + shlex.quote(owned_port_list))
    print("export QWQ_ANDROID_REVERSE_RECEIPT_DIGEST=" + shlex.quote(
        "sha256:" + hashlib.sha256(
            f"{target}\0{device_id}\0{port_list}".encode("utf-8")
        ).hexdigest()
    ))
    print("export QWQ_ANDROID_LOCAL_TARGET=" + shlex.quote(target))
    print("export ANDROID_LOCAL_GATEWAY_BASE_URL=" + shlex.quote(overrides["gatewayBaseUrl"]))
    print("export ANDROID_LOCAL_LEGAL_BASE_URL=" + shlex.quote(overrides["legalBaseUrl"]))
    print(
        "export ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL="
        + shlex.quote(overrides["mediaAvatarBaseUrl"])
    )
    print(
        "export ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL="
        + shlex.quote(overrides["mediaImageBaseUrl"])
    )
    print(
        "export ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL="
        + shlex.quote(overrides["mediaVideoBaseUrl"])
    )
    print(
        "export ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL="
        + shlex.quote(overrides["mediaUploadBaseUrl"])
    )
PY
  )" || {
    echo "[run] GATE_BLOCK: failed to resolve device-specific Remote topology." >&2
    exit 2
  }
  eval "$DEVICE_EXPORTS"
fi

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" \
   || "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  RUNTIME_STACKCTL_PYTHON="$(
    bash "$APP_DIR/scripts/ios/resolve_stackctl_python.sh"
  )" || {
    echo "[run] GATE_BLOCK: a compatible Python is required for device system trust." >&2
    exit 2
  }
  DEVICE_TRUST_PLATFORM="$QWQ_RUN_DEVICE_KIND"
  if [[ "$DEVICE_TRUST_PLATFORM" == "android_emulator" ]]; then
    DEVICE_TRUST_PLATFORM="android-emulator"
  fi
  DEVICE_TRUST_COMMAND=(
    "$RUNTIME_STACKCTL_PYTHON" "$ROOT_DIR/quwoquan_ops/cli/stackctl.py"
    --output-format json device-trust --target "$QWQ_LAUNCH_TARGET"
    --platform "$DEVICE_TRUST_PLATFORM" --action install --device "$DEVICE_ID"
    --lease-id "canonical-launcher:${DEVICE_ID}"
  )
  if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" ]]; then
    DEVICE_TRUST_COMMAND+=(--defer-endpoint-probe)
  elif [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
    DEVICE_TRUST_COMMAND+=(--allow-unprovisioned-system-trust)
  fi
  if ! PYTHONDONTWRITEBYTECODE=1 "${DEVICE_TRUST_COMMAND[@]}" >/dev/null; then
    echo "[run] GATE_BLOCK: failed to install target-bound device system trust." >&2
    exit 2
  fi
fi

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  export ANDROID_SERIAL="$DEVICE_ID"
  if [[ -z "$QWQ_ANDROID_LOCAL_PORTS" ]]; then
    echo "[run] GATE_BLOCK: Android topology did not provide reverse ports."
    exit 2
  fi
fi

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" \
   || "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  LEASE_COMMAND=(
    "$RUNTIME_STACKCTL_PYTHON" "$ROOT_DIR/quwoquan_ops/cli/stackctl.py"
    --output-format json consumer-lease acquire
    --target "$QWQ_LAUNCH_TARGET"
    --device "$DEVICE_ID"
    --consumer "$QWQ_RUN_CONSUMER_ID"
  )
  if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" ]]; then
    LEASE_COMMAND+=(
      --platform ios-simulator
      --bundle-id com.example.quwoquanApp
      --ports ""
    )
  else
    LEASE_COMMAND+=(
      --platform android
      --package-name com.quwoquan.quwoquan_app
      --ports "$QWQ_ANDROID_LOCAL_PORTS"
    )
  fi
  LEASE_JSON="$(PYTHONDONTWRITEBYTECODE=1 "${LEASE_COMMAND[@]}")"
  QWQ_CONSUMER_LEASE_ID="$(
    python3 - "$LEASE_JSON" <<'PY'
import json
import sys

lease_id = str((json.loads(sys.argv[1]).get("lease") or {}).get("leaseId") or "")
if not lease_id:
    raise SystemExit("consumer lease response is missing leaseId")
print(lease_id)
PY
  )"
  export QWQ_CONSUMER_LEASE_ID
  QWQ_CONSUMER_LEASE_ACQUIRED=1
fi

HANDOFF_CMD=(
  python3 "$APP_DIR/scripts/device/build_launcher_handoff.py"
  --env "$QWQ_APP_RUNTIME_ENV"
  --target "$QWQ_LAUNCH_TARGET"
  --launch-mode canonical_launcher
  --app-instance-id "$QWQ_APP_RUNTIME_ENV-run"
  --app-instance-namespace "$QWQ_APP_RUNTIME_ENV-run"
  --content-release-id "$QWQ_CONTENT_RELEASE_ID"
  --content-manifest-digest "$QWQ_CONTENT_MANIFEST_DIGEST"
  --content-readiness-receipt-digest \
  "$QWQ_CONTENT_READINESS_RECEIPT_DIGEST"
)
if [[ -n "$ANDROID_LOCAL_GATEWAY_BASE_URL" ]]; then
  HANDOFF_CMD+=(--gateway-base-url "$ANDROID_LOCAL_GATEWAY_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_LEGAL_BASE_URL" ]]; then
  HANDOFF_CMD+=(--legal-base-url "$ANDROID_LOCAL_LEGAL_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-avatar-base-url "$ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-image-base-url "$ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-video-base-url "$ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-upload-base-url "$ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL")
fi
if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  HANDOFF_CMD+=(
    --transport-required
    --reverse-expected-ports "$QWQ_ANDROID_REVERSE_EXPECTED_PORTS"
    --reverse-actual-ports "$QWQ_ANDROID_REVERSE_ACTUAL_PORTS"
    --reverse-receipt-digest "$QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"
    --consumer-lease-id "$QWQ_CONSUMER_LEASE_ID"
  )
fi

HANDOFF_JSON="$("${HANDOFF_CMD[@]}")"
HANDOFF_EXPORTS="$(
  python3 - "$HANDOFF_JSON" <<'PY'
import json
import shlex
import sys

handoff = json.loads(sys.argv[1])
print("ENTRYPOINT=" + shlex.quote(handoff["entrypoint"]))
print("LAUNCH_MODE=" + shlex.quote(handoff["launchMode"]))
print("DART_DEFINES_DIGEST=" + shlex.quote(handoff["dartDefinesDigest"]))
print("RUNTIME_CONFIG_DIGEST=" + shlex.quote(handoff["runtimeConfigDigest"]))
print("EFFECTIVE_LAUNCH_MANIFEST_DIGEST=" + shlex.quote(
    handoff["effectiveLaunchManifestDigest"]
))
print("EFFECTIVE_LAUNCH_MANIFEST_JSON=" + shlex.quote(json.dumps(
    handoff["effectiveLaunchManifest"],
    ensure_ascii=False,
    separators=(",", ":"),
)))
print("RECOVERY_BASE_URL=" + shlex.quote(handoff["recoveryBaseUrl"]))
print("PUBLIC_WEB_BASE_URL=" + shlex.quote(handoff["publicWebBaseUrl"]))
print("APP_DOWNLOAD_BASE_URL=" + shlex.quote(handoff["appDownloadBaseUrl"]))
print("DEFINES_JSON=" + shlex.quote(json.dumps(
    handoff["dartDefines"],
    ensure_ascii=False,
    separators=(",", ":"),
)))
PY
)" || {
  echo "[run] GATE_BLOCK: failed to parse launcher handoff." >&2
  exit 2
}
eval "$HANDOFF_EXPORTS"
export QWQ_APP_LAUNCH_MODE="$LAUNCH_MODE"
export QWQ_DART_DEFINES_DIGEST="$DART_DEFINES_DIGEST"
export QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST="$RUNTIME_CONFIG_DIGEST"
export QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST="$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
export QWQ_APP_RECOVERY_BASE_URL="$RECOVERY_BASE_URL"
export QWQ_APP_PUBLIC_WEB_URL="$PUBLIC_WEB_BASE_URL"
export QWQ_APP_DOWNLOAD_BASE_URL="$APP_DOWNLOAD_BASE_URL"
if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" == "1" ]]; then
  LEASE_BIND_COMMAND=(
    "${LEASE_COMMAND[@]}"
    --handoff-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  )
  if [[ -n "${QWQ_CONTENT_RELEASE_ID:-}" ]]; then
    LEASE_BIND_COMMAND+=(--release-id "$QWQ_CONTENT_RELEASE_ID")
  fi
  if [[ -n "${QWQ_CONTENT_MANIFEST_DIGEST:-}" ]]; then
    LEASE_BIND_COMMAND+=(--manifest-digest "$QWQ_CONTENT_MANIFEST_DIGEST")
  fi
  if [[ -n "${QWQ_CONTENT_READINESS_RECEIPT_DIGEST:-}" ]]; then
    LEASE_BIND_COMMAND+=(
      --readiness-receipt-digest "$QWQ_CONTENT_READINESS_RECEIPT_DIGEST"
    )
  fi
  PYTHONDONTWRITEBYTECODE=1 "${LEASE_BIND_COMMAND[@]}" >/dev/null
fi
VERIFY_HANDOFF_CMD=(
  python3 "$APP_DIR/scripts/device/verify_flutter_run_defines.py"
  --env "$QWQ_APP_RUNTIME_ENV"
  --target "$QWQ_LAUNCH_TARGET"
  --entrypoint "$ENTRYPOINT"
  --defines-digest "$DART_DEFINES_DIGEST"
  --runtime-config-digest "$RUNTIME_CONFIG_DIGEST"
  --effective-launch-manifest-json "$EFFECTIVE_LAUNCH_MANIFEST_JSON"
  --effective-launch-manifest-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  --defines-json "$DEFINES_JSON"
)
if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  VERIFY_HANDOFF_CMD+=(
    --transport-required
    --reverse-expected-ports "$QWQ_ANDROID_REVERSE_EXPECTED_PORTS"
    --reverse-actual-ports "$QWQ_ANDROID_REVERSE_ACTUAL_PORTS"
    --reverse-receipt-digest "$QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"
    --consumer-lease-id "$QWQ_CONSUMER_LEASE_ID"
  )
fi
"${VERIFY_HANDOFF_CMD[@]}"

DART_DEFINES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && DART_DEFINES+=("$line")
done < <(
  python3 - "$DEFINES_JSON" <<'PY'
import json
import sys
for key, value in json.loads(sys.argv[1]).items():
    print(f"--dart-define={key}={value}")
PY
)

flutter run \
  --no-pub \
  --target "$ENTRYPOINT" \
  --host-vmservice-port=8888 \
  --dds-port=8889 \
  "${DART_DEFINES[@]}" \
  "$@"
