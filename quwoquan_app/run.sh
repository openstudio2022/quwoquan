#!/usr/bin/env bash
# 使用 env-package-backed Alpha Remote 启动入口，避免裸跑漏掉 runtime/release 合同。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
export QWQ_APP_RUNTIME_ENV=alpha
export QWQ_LAUNCH_TARGET=alpha-local
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
      echo "[run] GATE_BLOCK: the Alpha launcher target is fixed by the production Remote handoff."
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

release_consumer_lease() {
  if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" != "1" ]]; then
    return
  fi
  if command -v adb >/dev/null 2>&1; then
    IFS=',' read -r -a reverse_ports <<< "$QWQ_ANDROID_LOCAL_PORTS"
    for port in "${reverse_ports[@]}"; do
      [[ -z "$port" ]] && continue
      if ! adb -s "$DEVICE_ID" reverse --remove "tcp:$port" >/dev/null 2>&1; then
        echo "[run] WARN: failed to remove owned adb reverse tcp:$port."
      fi
    done
  fi
  python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" consumer-lease release \
    --target alpha-local \
    --device "$DEVICE_ID" \
    --consumer "$QWQ_RUN_CONSUMER_ID" >/dev/null || \
    echo "[run] WARN: failed to release Android runtime consumer lease."
  QWQ_CONSUMER_LEASE_ACQUIRED=0
}

trap release_consumer_lease EXIT

if [[ -n "$DEVICE_ID" ]]; then
  DEVICE_EXPORTS="$(
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - "$DEVICE_ID" <<'PY'
import hashlib
import shlex
import sys

from quwoquan_ops.cli.lib.dev_up import (
    detect_device_kind,
    enable_android_adb_reverse,
    find_device,
    load_environment_topology,
    resolve_app_endpoint_overrides,
)

device_id = sys.argv[1].strip()
device = find_device(device_id, include_desktop=False) or {}
device_kind = detect_device_kind(
    device_id,
    target_platform=str(device.get("targetPlatform", "")),
    emulator=bool(device.get("emulator", False)) if device else None,
)
print(f"export QWQ_RUN_DEVICE_KIND={shlex.quote(device_kind)}")
if device_kind.startswith("android"):
    topology = load_environment_topology()
    ports = enable_android_adb_reverse(device_id, "alpha-local", topology=topology)
    overrides = resolve_app_endpoint_overrides("alpha", device_kind, topology=topology)
    port_list = ",".join(str(port) for port in ports)
    print("export QWQ_ANDROID_LOCAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_EXPECTED_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_ACTUAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_RECEIPT_DIGEST=" + shlex.quote(
        "sha256:" + hashlib.sha256(
            f"alpha-local\0{device_id}\0{port_list}".encode("utf-8")
        ).hexdigest()
    ))
    print("export QWQ_ANDROID_LOCAL_TARGET=alpha-local")
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

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  export ANDROID_SERIAL="$DEVICE_ID"
  if [[ -z "$QWQ_ANDROID_LOCAL_PORTS" ]]; then
    echo "[run] GATE_BLOCK: Android topology did not provide reverse ports."
    exit 2
  fi
  LEASE_JSON="$(
    python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
      consumer-lease acquire \
      --target alpha-local \
      --device "$DEVICE_ID" \
      --consumer "$QWQ_RUN_CONSUMER_ID" \
      --package-name com.quwoquan.quwoquan_app \
      --ports "$QWQ_ANDROID_LOCAL_PORTS"
  )"
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

echo "[run] reading Alpha readiness (diagnostic only)..."
if ! python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" status \
  --target alpha-local; then
  echo "[run] WARN: Alpha is not ready or readiness could not be read. The App will still launch and surface runtime errors; release/UAT readiness remains blocked." >&2
fi
echo "[run] Alpha readiness above is diagnostic only; environment lifecycle remains owned by stackctl workflows."

HANDOFF_CMD=(
  python3 "$APP_DIR/scripts/device/build_launcher_handoff.py"
  --env alpha
  --target alpha-local
  --launch-mode canonical_launcher
  --app-instance-id alpha-run
  --app-instance-namespace alpha-run
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
VERIFY_HANDOFF_CMD=(
  python3 "$APP_DIR/scripts/device/verify_flutter_run_defines.py"
  --env alpha
  --target alpha-local
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
