#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
runtime_topology="$ROOT/quwoquan_ops/environments/gamma/runtime.yaml"
if [[ ! -f "$runtime_topology" ]]; then
  echo "[local-gamma:device-uat] GATE_BLOCK: gamma runtime topology is missing" >&2
  exit 2
fi

topology_public_bases="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

bases = get_target(load_environment_topology(), "gamma-local")["publicBases"]
values = [
    bases["api"],
    bases["productOps"],
    bases["mediaAvatar"],
    bases["mediaImage"],
    bases["mediaVideo"],
    bases["mediaUpload"],
    bases["rtc"],
]
if any(not isinstance(value, str) or not value.strip() for value in values):
    raise SystemExit("resolved gamma-local publicBases contains an empty value")
print("\t".join(values))
PY
)"
IFS=$'\t' read -r topology_gateway_base_url topology_product_ops_base_url topology_media_avatar_base_url topology_media_image_base_url topology_media_video_base_url topology_media_upload_base_url topology_rtc_media_connection_url <<< "$topology_public_bases"

if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "local-gamma-device-uat", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi
GAMMA_RUN_ROOT="$QWQ_RUN_ROOT"
REPORT="${LOCAL_GAMMA_DEVICE_UAT_REPORT:-$GAMMA_RUN_ROOT/device_uat_report.json}"
CASE_RESULT_HELPER="$ROOT/quwoquan_app/scripts/gamma/gamma_case_result.py"
GATEWAY_BASE_URL="$topology_gateway_base_url"
PRODUCT_OPS_BASE_URL="$topology_product_ops_base_url"
MEDIA_AVATAR_BASE_URL="$topology_media_avatar_base_url"
MEDIA_IMAGE_BASE_URL="$topology_media_image_base_url"
MEDIA_VIDEO_BASE_URL="$topology_media_video_base_url"
MEDIA_UPLOAD_BASE_URL="$topology_media_upload_base_url"
RTC_MEDIA_CONNECTION_URL="$topology_rtc_media_connection_url"
# Local Gamma owns its anonymous session inside the device runtime through the
# public user-service boundary. Never inherit host credentials: Flutter expands
# Dart defines into child process arguments, which would expose a bearer token.
unset TEST_AUTH_TOKEN TEST_REFRESH_TOKEN APP_CURRENT_OWNER_ID APP_CURRENT_PERSONA_ID
PATROL_TARGET="${LOCAL_GAMMA_DEVICE_UAT_TARGET:-test/user_acceptance/service/content_service/content/feed_delivery_page/feed_load__user_acceptance_test.dart}"
PATROL_INSTALL_ID="${QWQ_PATROL_INSTALL_ID:-}"
RELEASE_UAT_CASES=""
REMOTE_API_EVIDENCE_REPORT="${LOCAL_GAMMA_REMOTE_API_EVIDENCE_REPORT:-}"
TARGET_UAT_BINDING="${LOCAL_GAMMA_TARGET_UAT_BINDING:-}"
TARGET_EXPLICIT=0
DEVICE_ID="${LOCAL_GAMMA_DEVICE_UAT_DEVICE_ID:-}"
PLATFORM="${LOCAL_GAMMA_DEVICE_UAT_PLATFORM:-all}"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: quwoquan_app/scripts/gamma/run_local_gamma_device_uat.sh [options]

Options:
  --device-id <id>          Run Patrol on a specific Flutter device.
  --platform <name>         android / ios / all (default: all).
  --target <path>           Patrol target file or directory.
  --patrol-install-id <tpl> One-run install identity template; account closure requires {device}.
  --release-uat-cases <path> Gamma data-release generated homepage_verification_cases.json.
  --remote-api-evidence-report <path> Passed Remote API UAT report to attach request/trace evidence.
  --target-uat-binding <path> Exact canonical TargetUatBinding for one device slot.
  --report <path>           Write the Patrol report to this runtime evidence path.
  --gateway-base-url <url>  Mirror gateway URL.
  --product-ops-base-url <url>
  --media-avatar-base-url <url>
  --media-image-base-url <url>
  --media-video-base-url <url>
  --media-upload-base-url <url>
  --rtc-media-connection-url <url>
  --dry-run                 Validate command construction only.
  --help                    Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device-id) DEVICE_ID="${2:-}"; shift 2 ;;
    --platform) PLATFORM="${2:-}"; shift 2 ;;
    --target) PATROL_TARGET="${2:-}"; TARGET_EXPLICIT=1; shift 2 ;;
    --patrol-install-id) PATROL_INSTALL_ID="${2:-}"; shift 2 ;;
    --release-uat-cases) RELEASE_UAT_CASES="${2:-}"; shift 2 ;;
    --remote-api-evidence-report) REMOTE_API_EVIDENCE_REPORT="${2:-}"; shift 2 ;;
    --target-uat-binding) TARGET_UAT_BINDING="${2:-}"; shift 2 ;;
    --report) REPORT="${2:-}"; shift 2 ;;
    --gateway-base-url) GATEWAY_BASE_URL="${2:-}"; shift 2 ;;
    --product-ops-base-url) PRODUCT_OPS_BASE_URL="${2:-}"; shift 2 ;;
    --media-avatar-base-url) MEDIA_AVATAR_BASE_URL="${2:-}"; shift 2 ;;
    --media-image-base-url) MEDIA_IMAGE_BASE_URL="${2:-}"; shift 2 ;;
    --media-video-base-url) MEDIA_VIDEO_BASE_URL="${2:-}"; shift 2 ;;
    --media-upload-base-url) MEDIA_UPLOAD_BASE_URL="${2:-}"; shift 2 ;;
    --rtc-media-connection-url) RTC_MEDIA_CONNECTION_URL="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

report_stem="${REPORT%.json}"
PATROL_REPORT="${LOCAL_GAMMA_DEVICE_UAT_PATROL_REPORT:-${report_stem}.patrol.json}"
IDENTITY_SNAPSHOT="${LOCAL_GAMMA_DEVICE_UAT_IDENTITY_SNAPSHOT:-${report_stem}.identity.json}"

case_result_helper() {
  PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -B "$CASE_RESULT_HELPER" "$@"
}


require_canonical_endpoint() {
  local name="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" != "$expected" ]]; then
    echo "[local-gamma:device-uat] GATE_BLOCK: $name must equal gamma-local topology projection" >&2
    exit 2
  fi
}
require_canonical_endpoint gateway "$GATEWAY_BASE_URL" "$topology_gateway_base_url"
require_canonical_endpoint productOps "$PRODUCT_OPS_BASE_URL" "$topology_product_ops_base_url"
require_canonical_endpoint mediaAvatar "$MEDIA_AVATAR_BASE_URL" "$topology_media_avatar_base_url"
require_canonical_endpoint mediaImage "$MEDIA_IMAGE_BASE_URL" "$topology_media_image_base_url"
require_canonical_endpoint mediaVideo "$MEDIA_VIDEO_BASE_URL" "$topology_media_video_base_url"
require_canonical_endpoint mediaUpload "$MEDIA_UPLOAD_BASE_URL" "$topology_media_upload_base_url"
require_canonical_endpoint rtc "$RTC_MEDIA_CONNECTION_URL" "$topology_rtc_media_connection_url"


if [[ -z "$TARGET_UAT_BINDING" ]]; then
  echo "[local-gamma:device-uat] GATE_BLOCK: --target-uat-binding is required" >&2
  exit 2
fi
if [[ -z "$DEVICE_ID" ]]; then
  echo "[local-gamma:device-uat] GATE_BLOCK: one explicit --device-id is required for exact slot binding" >&2
  exit 2
fi
if [[ "$PLATFORM" == "all" ]]; then
  echo "[local-gamma:device-uat] GATE_BLOCK: --platform must be android or ios for exact slot binding" >&2
  exit 2
fi

set +e
case_result_helper prepare-device-uat \
  --report "$REPORT" \
  --identity-snapshot "$IDENTITY_SNAPSHOT" \
  --patrol-report "$PATROL_REPORT"
prepare_status=$?
set -e
if [[ "$prepare_status" -ne 0 ]]; then
  echo "[local-gamma:device-uat] GATE_BLOCK: active candidate/startup identity is unavailable" >&2
  exit 2
fi

if [[ -n "$RELEASE_UAT_CASES" ]]; then
  release_homepage_target="test/user_acceptance/service/entity_service/entity_homepage/homepage/release_homepage__consumer_render__functional__user_acceptance_test.dart"
  if [[ "$TARGET_EXPLICIT" == "1" && "$PATROL_TARGET" != "$release_homepage_target" ]]; then
    echo "[local-gamma:device-uat] GATE_BLOCK: --release-uat-cases requires $release_homepage_target" >&2
    exit 2
  fi
  PATROL_TARGET="$release_homepage_target"
fi

_flutter_bin="$(command -v flutter || true)"
if ! command -v dart >/dev/null 2>&1 && [[ -n "$_flutter_bin" ]] && [[ -x "${_flutter_bin%/flutter}/dart" ]]; then
  # Flutter bundles Dart, but desktop shells do not always add it to PATH.
  # Patrol is a Dart global executable, so expose the paired SDK before
  # discovering the pub-cache bin directory.
  PATH="${_flutter_bin%/flutter}:$PATH"
fi

_patrol_cache_bin=""
if command -v dart >/dev/null 2>&1; then
  _cache_root="${PUB_CACHE:-$HOME/.pub-cache}"
  if [[ -n "$_cache_root" && -d "$_cache_root/bin" ]]; then
    PATH="${PATH}:$_cache_root/bin"
    _patrol_cache_bin="$_cache_root/bin"
  fi
fi

if ! command -v patrol >/dev/null 2>&1; then
  echo "[local-gamma:device-uat] GATE_BLOCK: patrol CLI not found" >&2
  exit 2
fi
if ! command -v flutter >/dev/null 2>&1; then
  echo "[local-gamma:device-uat] GATE_BLOCK: flutter CLI not found" >&2
  exit 2
fi

export MEDIA_AVATAR_CDN_BASE_URL="$MEDIA_AVATAR_BASE_URL"
mkdir -p "$(dirname "$PATROL_REPORT")"

cmd=(
  python3
  quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py
  --report "$PATROL_REPORT"
  --target "$PATROL_TARGET"
  --env-name "local-gamma"
  --runtime-env "gamma"
  --api-contract-env "gamma"
  --platform "$PLATFORM"
  --gateway-base-url "$GATEWAY_BASE_URL"
  --product-ops-base-url "$PRODUCT_OPS_BASE_URL"
  --media-avatar-base-url "$MEDIA_AVATAR_BASE_URL"
  --media-image-base-url "$MEDIA_IMAGE_BASE_URL"
  --media-video-base-url "$MEDIA_VIDEO_BASE_URL"
  --media-upload-base-url "$MEDIA_UPLOAD_BASE_URL"
  --rtc-media-connection-url "$RTC_MEDIA_CONNECTION_URL"
)
if [[ -n "$DEVICE_ID" ]]; then
  cmd+=(--device-id "$DEVICE_ID")
fi
if [[ -n "$RELEASE_UAT_CASES" ]]; then
  cmd+=(--release-uat-cases "$RELEASE_UAT_CASES")
fi
if [[ -n "$REMOTE_API_EVIDENCE_REPORT" ]]; then
  cmd+=(--remote-api-evidence-report "$REMOTE_API_EVIDENCE_REPORT")
fi
if [[ -n "$PATROL_INSTALL_ID" ]]; then
  cmd+=(--patrol-install-id "$PATROL_INSTALL_ID")
fi
if [[ "$DRY_RUN" == "1" ]]; then
  cmd+=(--dry-run)
fi

set +e
cd "$ROOT"
"${cmd[@]}"
patrol_status=$?
set -e

finalize_args=(
  finalize-device-uat
  --report "$REPORT"
  --identity-snapshot "$IDENTITY_SNAPSHOT"
  --patrol-report "$PATROL_REPORT"
  --runner-exit-code "$patrol_status"
  --target-uat-binding "$TARGET_UAT_BINDING"
)
if [[ "$DRY_RUN" == "1" ]]; then
  finalize_args+=(--dry-run)
fi
set +e
case_result_helper "${finalize_args[@]}"
status=$?
set -e

if [[ "$status" -eq 0 && "$patrol_status" -eq 0 ]]; then
  echo "[local-gamma:device-uat] status: passed"
else
  echo "[local-gamma:device-uat] status: GATE_BLOCK/failed" >&2
fi
exit "$status"
