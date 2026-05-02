#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/quwoquan_app"
REPORT="${LOCAL_GAMMA_T4_REPORT:-$ROOT/artifacts/local-gamma/t4_report.json}"
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-http://127.0.0.1:18080}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-http://127.0.0.1:18086}"
MEDIA_BASE_URL="${LOCAL_GAMMA_MEDIA_BASE_URL:-http://127.0.0.1:80/media}"
TEST_AUTH_TOKEN="${LOCAL_GAMMA_TEST_AUTH_TOKEN:-${TEST_AUTH_TOKEN:-local-gamma-token}}"
PATROL_TARGET="${LOCAL_GAMMA_T4_TARGET:-test/patrol/discovery/feed_load_test.dart}"
DEVICE_ID="${LOCAL_GAMMA_T4_DEVICE_ID:-}"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: scripts/run_local_gamma_t4.sh [options]

Options:
  --device-id <id>          Run Patrol on a specific Flutter device.
  --target <path>           Patrol target file or directory.
  --gateway-base-url <url>  Mirror gateway URL.
  --product-ops-base-url <url>
  --media-base-url <url>
  --dry-run                 Validate command construction only.
  --help                    Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device-id) DEVICE_ID="${2:-}"; shift 2 ;;
    --target) PATROL_TARGET="${2:-}"; shift 2 ;;
    --gateway-base-url) GATEWAY_BASE_URL="${2:-}"; shift 2 ;;
    --product-ops-base-url) PRODUCT_OPS_BASE_URL="${2:-}"; shift 2 ;;
    --media-base-url) MEDIA_BASE_URL="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

write_report() {
  local status="$1"
  local reason="${2:-}"
  mkdir -p "$(dirname "$REPORT")"
  python3 - "$REPORT" "$status" "$reason" "$GATEWAY_BASE_URL" "$PRODUCT_OPS_BASE_URL" "$MEDIA_BASE_URL" "$DEVICE_ID" <<'PY'
import json
import sys
from pathlib import Path

path, status, reason, gateway, product_ops, media, device = sys.argv[1:8]
report = {
    "status": status,
    "reason": reason,
    "gatewayBaseUrl": gateway,
    "productOpsBaseUrl": product_ops,
    "mediaBaseUrl": media,
    "deviceId": device,
}
Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

if [[ "$DRY_RUN" == "1" ]]; then
  write_report "passed" "dry-run"
  echo "[local-gamma:t4] dry-run report: $REPORT"
  exit 0
fi

if ! command -v patrol >/dev/null 2>&1; then
  write_report "gate_block" "patrol CLI not found"
  echo "[local-gamma:t4] GATE_BLOCK: patrol CLI not found" >&2
  exit 2
fi
if ! command -v flutter >/dev/null 2>&1; then
  write_report "gate_block" "flutter CLI not found"
  echo "[local-gamma:t4] GATE_BLOCK: flutter CLI not found" >&2
  exit 2
fi

if [[ -z "$DEVICE_ID" ]] && command -v xcrun >/dev/null 2>&1; then
  DEVICE_ID="$(xcrun simctl list devices available --json | python3 -c 'import json,re,sys
data=json.load(sys.stdin).get("devices", {})
ios=[]
for runtime, devices in data.items():
    match=re.search(r"iOS-(\d+(?:-\d+)*)$", runtime)
    if not match:
        continue
    version=tuple(int(part) for part in match.group(1).split("-"))
    for index, device in enumerate(devices):
        if device.get("isAvailable") and device.get("udid"):
            ios.append((version, device.get("state") == "Booted", device.get("name") == "iPhone 17 Pro", -index, device["udid"]))
if ios:
    ios.sort(reverse=True)
    print(ios[0][-1])
')"
fi
if [[ -z "$DEVICE_ID" ]]; then
  DEVICE_ID="$(cd "$APP_DIR" && flutter devices --machine | python3 -c 'import json,sys; data=json.load(sys.stdin); mobile=[d for d in data if d.get("targetPlatform","").startswith(("ios","android"))]; print(mobile[0]["id"] if mobile else "")')"
fi
if [[ -z "$DEVICE_ID" ]]; then
  write_report "gate_block" "no iOS/Android simulator or device available"
  echo "[local-gamma:t4] GATE_BLOCK: no iOS/Android simulator or device available" >&2
  exit 2
fi

set +e
cd "$APP_DIR"
patrol test -t "$PATROL_TARGET" \
  -d "$DEVICE_ID" \
  --dart-define=RUN_T4_PATROL=true \
  --dart-define=APP_RUNTIME_ENV=gamma \
  --dart-define=APP_DATA_SOURCE=remote \
  --dart-define=API_CONTRACT_ENV=gamma \
  "--dart-define=CLOUD_GATEWAY_BASE_URL=${GATEWAY_BASE_URL}" \
  "--dart-define=API_CONTRACT_BASE_URL=${GATEWAY_BASE_URL}" \
  "--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=${PRODUCT_OPS_BASE_URL}" \
  "--dart-define=TEST_AUTH_TOKEN=${TEST_AUTH_TOKEN}" \
  "--dart-define=MEDIA_AVATAR_CDN_BASE_URL=${MEDIA_BASE_URL}" \
  "--dart-define=MEDIA_IMAGE_CDN_BASE_URL=${MEDIA_BASE_URL}" \
  "--dart-define=MEDIA_VIDEO_CDN_BASE_URL=${MEDIA_BASE_URL}" \
  "--dart-define=MEDIA_UPLOAD_BASE_URL=${MEDIA_BASE_URL}"
status=$?
set -e

if [[ "$status" -eq 0 ]]; then
  write_report "passed" ""
  echo "[local-gamma:t4] status: passed"
else
  write_report "failed" "patrol exited with $status"
  echo "[local-gamma:t4] status: failed" >&2
fi
exit "$status"
