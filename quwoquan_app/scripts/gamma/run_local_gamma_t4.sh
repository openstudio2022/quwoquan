#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "local-gamma-t4", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi
GAMMA_RUN_ROOT="$QWQ_RUN_ROOT"
REPORT="${LOCAL_GAMMA_T4_REPORT:-$GAMMA_RUN_ROOT/t4_report.json}"
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-https://gamma-api.quwoquan-env.test:19000}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-https://gamma-product-ops.quwoquan-env.test:19010}"
MEDIA_BASE_URL="${LOCAL_GAMMA_MEDIA_BASE_URL:-https://gamma-image.quwoquan-env.test:19100}"
# Local Gamma owns its anonymous session inside the device runtime through the
# public user-service boundary. Never inherit host credentials: Flutter expands
# Dart defines into child process arguments, which would expose a bearer token.
unset TEST_AUTH_TOKEN TEST_REFRESH_TOKEN APP_CURRENT_OWNER_ID APP_CURRENT_SUB_ACCOUNT_ID
PATROL_TARGET="${LOCAL_GAMMA_T4_TARGET:-test/user_acceptance/patrol/discovery/feed_load__user_acceptance_test.dart}"
RELEASE_UAT_CASES=""
TARGET_EXPLICIT=0
DEVICE_ID="${LOCAL_GAMMA_T4_DEVICE_ID:-}"
PLATFORM="${LOCAL_GAMMA_T4_PLATFORM:-all}"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: quwoquan_app/scripts/gamma/run_local_gamma_t4.sh [options]

Options:
  --device-id <id>          Run Patrol on a specific Flutter device.
  --platform <name>         android / ios / all (default: all).
  --target <path>           Patrol target file or directory.
  --release-uat-cases <path> Gamma data-release generated app_uat_cases.json.
  --report <path>           Write the Patrol report to this runtime evidence path.
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
    --platform) PLATFORM="${2:-}"; shift 2 ;;
    --target) PATROL_TARGET="${2:-}"; TARGET_EXPLICIT=1; shift 2 ;;
    --release-uat-cases) RELEASE_UAT_CASES="${2:-}"; shift 2 ;;
    --report) REPORT="${2:-}"; shift 2 ;;
    --gateway-base-url) GATEWAY_BASE_URL="${2:-}"; shift 2 ;;
    --product-ops-base-url) PRODUCT_OPS_BASE_URL="${2:-}"; shift 2 ;;
    --media-base-url) MEDIA_BASE_URL="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -n "$RELEASE_UAT_CASES" ]]; then
  two_province_target="test/user_acceptance/patrol/entity/two_province_homepage__rollout_render__functional__user_acceptance_test.dart"
  if [[ "$TARGET_EXPLICIT" == "1" && "$PATROL_TARGET" != "$two_province_target" ]]; then
    echo "[local-gamma:t4] GATE_BLOCK: --release-uat-cases requires $two_province_target" >&2
    exit 2
  fi
  PATROL_TARGET="$two_province_target"
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
  echo "[local-gamma:t4] GATE_BLOCK: patrol CLI not found" >&2
  exit 2
fi
if ! command -v flutter >/dev/null 2>&1; then
  echo "[local-gamma:t4] GATE_BLOCK: flutter CLI not found" >&2
  exit 2
fi

export MEDIA_AVATAR_CDN_BASE_URL="$MEDIA_BASE_URL"
mkdir -p "$(dirname "$REPORT")"

cmd=(
  python3
  quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py
  --report "$REPORT"
  --target "$PATROL_TARGET"
  --env-name "local-gamma"
  --runtime-env "gamma"
  --api-contract-env "gamma"
  --data-source "remote"
  --platform "$PLATFORM"
  --gateway-base-url "$GATEWAY_BASE_URL"
  --product-ops-base-url "$PRODUCT_OPS_BASE_URL"
  --media-base-url "$MEDIA_BASE_URL"
)
if [[ -n "$DEVICE_ID" ]]; then
  cmd+=(--device-id "$DEVICE_ID")
fi
if [[ -n "$RELEASE_UAT_CASES" ]]; then
  cmd+=(--release-uat-cases "$RELEASE_UAT_CASES")
fi
if [[ "$DRY_RUN" == "1" ]]; then
  cmd+=(--dry-run)
fi

set +e
cd "$ROOT"
"${cmd[@]}"
status=$?
set -e

if [[ "$status" -eq 0 ]]; then
  echo "[local-gamma:t4] status: passed"
else
  echo "[local-gamma:t4] status: failed" >&2
fi
exit "$status"
