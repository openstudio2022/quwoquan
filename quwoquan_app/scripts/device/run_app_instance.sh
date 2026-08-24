#!/usr/bin/env bash
# App instance adapter: non-Prod delegates to run.sh; Prod consumes an exact Release artifact.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
STATE_ROOT="${APP_INSTANCE_STATE_ROOT:-$QWQ_OUTPUT_ROOT/env/repo/local/app-instances/process}"

ENV_NAME=""
TARGET_NAME=""
DEVICE_ID=""
RUN_MODE="content-live"
ARTIFACT_MANIFEST=""
LAUNCH_RECEIPT=""
LAUNCH_LOG_REF=""
INSTANCE_NAMESPACE="${APP_INSTANCE_NAMESPACE:-manual}"
SERVICE_MODE="${APP_INSTANCE_SERVICE_MODE:-app-only}"
ROLLOUT_MODE="${APP_ROLLOUT_MODE:-}"
GATEWAY_BASE_URL=""
LEGAL_BASE_URL=""
MEDIA_AVATAR_BASE_URL=""
MEDIA_IMAGE_BASE_URL=""
MEDIA_VIDEO_BASE_URL=""
MEDIA_UPLOAD_BASE_URL=""
CURRENT_USER_ID=""

usage() {
  cat <<'EOF'
Usage:
  run_app_instance.sh --env <alpha|beta|gamma|prod> --target <target> \
    --device-id <id> [--mode content-live|ui-only] [--artifact-manifest <path>]

Non-Prod delegates to quwoquan_app/run.sh. Android prod-sim requires the exact
stackctl Release emulator manifest. iOS Release/Profile simulator is unsupported;
prod-hosted never permits direct Flutter execution or Debug.

Legacy endpoint override options remain input-validation only; they are never
used to assemble a second Flutter command or a second runtime configuration.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_NAME="${2:-}"; shift 2 ;;
    --target) TARGET_NAME="${2:-}"; shift 2 ;;
    --device-id) DEVICE_ID="${2:-}"; shift 2 ;;
    --mode) RUN_MODE="${2:-}"; shift 2 ;;
    --artifact-manifest) ARTIFACT_MANIFEST="${2:-}"; shift 2 ;;
    --launch-receipt) LAUNCH_RECEIPT="${2:-}"; shift 2 ;;
    --launch-log-ref) LAUNCH_LOG_REF="${2:-}"; shift 2 ;;
    --gateway-base-url) GATEWAY_BASE_URL="${2:-}"; shift 2 ;;
    --legal-base-url) LEGAL_BASE_URL="${2:-}"; shift 2 ;;
    --media-avatar-base-url) MEDIA_AVATAR_BASE_URL="${2:-}"; shift 2 ;;
    --media-image-base-url) MEDIA_IMAGE_BASE_URL="${2:-}"; shift 2 ;;
    --media-video-base-url) MEDIA_VIDEO_BASE_URL="${2:-}"; shift 2 ;;
    --media-upload-base-url) MEDIA_UPLOAD_BASE_URL="${2:-}"; shift 2 ;;
    --current-user-id) CURRENT_USER_ID="${2:-}"; shift 2 ;;
    --instance-namespace) INSTANCE_NAMESPACE="${2:-}"; shift 2 ;;
    --service-mode) SERVICE_MODE="${2:-}"; shift 2 ;;
    --rollout-mode) ROLLOUT_MODE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "GATE_BLOCK: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$ENV_NAME:$TARGET_NAME" in
  alpha:alpha-local|beta:beta-local|gamma:gamma-local|prod:prod-sim|prod:prod-hosted) ;;
  *)
    echo "GATE_BLOCK: --target must explicitly match --env." >&2
    exit 2
    ;;
esac
case "$RUN_MODE" in
  content-live|ui-only) ;;
  *) echo "GATE_BLOCK: --mode requires content-live|ui-only." >&2; exit 2 ;;
esac
if [[ -z "$DEVICE_ID" ]]; then
  echo "GATE_BLOCK: --device-id is required." >&2
  exit 2
fi

if [[ "$TARGET_NAME" == "prod-hosted" ]]; then
  echo "APP.LAUNCH.prod_hosted_flutter_forbidden: prod-hosted consumes only signed artifact, install receipt and explicit rollout authorization." >&2
  exit 2
fi
if [[ "$TARGET_NAME" == "prod-sim" && -z "$ARTIFACT_MANIFEST" ]]; then
  echo "APP.LAUNCH.prod_artifact_required: prod-sim requires --artifact-manifest from stackctl package --kind app-artifact." >&2
  exit 2
fi

DEVICE_PLATFORM="$({
  PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - "$DEVICE_ID" <<'PY'
import sys
from quwoquan_ops.cli.lib.dev_up import find_device

device = find_device(sys.argv[1], include_desktop=False)
if device is None:
    raise SystemExit("APP.LAUNCH.device_unavailable")
platform = str(device.get("targetPlatform") or "").lower()
if platform == "ios":
    print("ios")
elif platform.startswith("android"):
    print("android")
else:
    raise SystemExit("APP.LAUNCH.platform_unsupported")
PY
} )" || exit 2

if [[ -z "$LAUNCH_RECEIPT" ]]; then
  safe_device="$(printf '%s' "$DEVICE_ID" | tr -c 'A-Za-z0-9._-' '_')"
  LAUNCH_RECEIPT="$QWQ_OUTPUT_ROOT/env/repo/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$-${TARGET_NAME}-${safe_device}-app-launch/attempt.json"
fi

# 本地 target 的 endpoint 都是 public 域名走本地栈，证书链在启动前必须成立：
# 等到 App 起来后再失败，暴露出来的是难以归因的网络错误而不是缺失的信任材料。
# prod-hosted 已在上面退出，prod-sim 消费的是已签名制品，两者都不在此校验面。
if [[ "$TARGET_NAME" != "prod-sim" ]]; then
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/lib/public_domain_tls.py" verify \
    --target "$TARGET_NAME" >/dev/null || exit $?
fi

if [[ "$TARGET_NAME" == "prod-sim" ]]; then
  command=(
    python3 "$APP_DIR/scripts/device/launch_release_artifact.py"
    --manifest "$ARTIFACT_MANIFEST"
    --device "$DEVICE_ID"
    --platform "$DEVICE_PLATFORM"
    --receipt "$LAUNCH_RECEIPT"
  )
  [[ -z "$LAUNCH_LOG_REF" ]] || command+=(--log-ref "$LAUNCH_LOG_REF")
  exec "${command[@]}"
fi

# Endpoint options are intentionally not forwarded. run.sh rebuilds and verifies the
# canonical launcher handoff from target topology, including CLOUD_GATEWAY_BASE_URL,
# APP_LEGAL_BASE_URL and the four media endpoint fields.
for legacy_override in \
  "$GATEWAY_BASE_URL" "$LEGAL_BASE_URL" "$MEDIA_AVATAR_BASE_URL" \
  "$MEDIA_IMAGE_BASE_URL" "$MEDIA_VIDEO_BASE_URL" "$MEDIA_UPLOAD_BASE_URL" \
  "$CURRENT_USER_ID" "$ROLLOUT_MODE"; do
  if [[ -n "$legacy_override" ]]; then
    echo "[app-instance] WARN: legacy override was ignored; canonical run.sh owns runtime handoff." >&2
    break
  fi
done

safe_device="$(printf '%s' "$DEVICE_ID" | tr -c 'A-Za-z0-9._-' '_')"
STATE_FILE="$STATE_ROOT/$ENV_NAME/$safe_device.json"
mkdir -p "$(dirname "$STATE_FILE")"
python3 - "$STATE_FILE" "$ENV_NAME" "$TARGET_NAME" "$DEVICE_ID" "$INSTANCE_NAMESPACE" "$SERVICE_MODE" "$$" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
pid = int(sys.argv[7])
payload = {
    "schema": "app-instance-state",
    "env": sys.argv[2],
    "target": sys.argv[3],
    "deviceId": sys.argv[4],
    "instanceId": f"{sys.argv[2]}-{path.stem}",
    "instanceNamespace": sys.argv[5],
    "serviceMode": sys.argv[6],
    "pid": pid,
    "pgid": os.getpgid(pid),
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
export QWQ_APP_INSTANCE_STATE_FILE="$STATE_FILE"

command=(
  bash "$APP_DIR/run.sh"
  --env "$ENV_NAME"
  --target "$TARGET_NAME"
  --mode "$RUN_MODE"
  --launch-receipt "$LAUNCH_RECEIPT"
)
[[ -z "$LAUNCH_LOG_REF" ]] || command+=(--launch-log-ref "$LAUNCH_LOG_REF")
command+=(-d "$DEVICE_ID")
exec "${command[@]}"
