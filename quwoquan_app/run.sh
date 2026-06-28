#!/usr/bin/env bash
# 使用 env-package-backed alpha 启动入口，避免直接裸跑 flutter run 漏掉 runtime 合同。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"

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

DEVICE_ID="$(parse_flutter_device_id "$@")"

bash "$ROOT_DIR/agent_ops/deploy/alpha/start_alpha_mock_stack.sh" up

ANDROID_LOCAL_GATEWAY_BASE_URL=""
ANDROID_LOCAL_LEGAL_BASE_URL=""
ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL=""
ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL=""
ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL=""
ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL=""

if [[ -n "$DEVICE_ID" ]]; then
  eval "$(
    python3 - "$DEVICE_ID" <<'PY'
import shlex
import sys

from agent_ops.deploy.lib.dev_up import (
    detect_device_kind,
    enable_android_adb_reverse,
    find_device,
    load_environment_topology,
    local_target_android_debug_ca_cert,
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
    enable_android_adb_reverse(device_id, "alpha-local", topology=topology)
    overrides = resolve_app_endpoint_overrides("alpha", device_kind, topology=topology)
    ca_path = local_target_android_debug_ca_cert("alpha-local")
    print("export QWQ_ANDROID_LOCAL_ENV_CA_PATH=" + shlex.quote(str(ca_path)))
    print("export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1")
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
  )"
fi

DART_DEFINES=()
DEFINE_CMD=(
  python3 "$APP_DIR/scripts/env/print_app_env_dart_defines.py"
  --env alpha
  --format args
  --app-instance-id alpha-run
  --app-instance-namespace alpha-run
)
if [[ -n "$ANDROID_LOCAL_GATEWAY_BASE_URL" ]]; then
  DEFINE_CMD+=(--gateway-base-url "$ANDROID_LOCAL_GATEWAY_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_LEGAL_BASE_URL" ]]; then
  DEFINE_CMD+=(--legal-base-url "$ANDROID_LOCAL_LEGAL_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL" ]]; then
  DEFINE_CMD+=(--media-avatar-base-url "$ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL" ]]; then
  DEFINE_CMD+=(--media-image-base-url "$ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL" ]]; then
  DEFINE_CMD+=(--media-video-base-url "$ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL" ]]; then
  DEFINE_CMD+=(--media-upload-base-url "$ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL")
fi
while IFS= read -r line; do
  [[ -n "$line" ]] && DART_DEFINES+=("$line")
done < <("${DEFINE_CMD[@]}")

exec flutter run \
  --no-pub \
  --host-vmservice-port=8888 \
  --dds-port=8889 \
  "${DART_DEFINES[@]}" \
  "$@"
