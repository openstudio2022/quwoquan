#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
REPORT="${LOCAL_GAMMA_T4_REPORT:-$ROOT/artifacts/local-gamma/t4_report.json}"
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-http://127.0.0.1:18080}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-http://127.0.0.1:18086}"
MEDIA_BASE_URL="${LOCAL_GAMMA_MEDIA_BASE_URL:-http://127.0.0.1:80/media}"
TEST_AUTH_TOKEN="${LOCAL_GAMMA_TEST_AUTH_TOKEN:-${TEST_AUTH_TOKEN:-local-gamma-token}}"
PATROL_TARGET="${LOCAL_GAMMA_T4_TARGET:-test/patrol/discovery/feed_load_test.dart}"
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
    --target) PATROL_TARGET="${2:-}"; shift 2 ;;
    --gateway-base-url) GATEWAY_BASE_URL="${2:-}"; shift 2 ;;
    --product-ops-base-url) PRODUCT_OPS_BASE_URL="${2:-}"; shift 2 ;;
    --media-base-url) MEDIA_BASE_URL="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

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
  agent_ops/deploy/gamma/run_gamma_patrol_matrix_ci.py
  --report "$REPORT"
  --target "$PATROL_TARGET"
  --env-name "local-gamma"
  --platform "$PLATFORM"
  --gateway-base-url "$GATEWAY_BASE_URL"
  --product-ops-base-url "$PRODUCT_OPS_BASE_URL"
  --test-auth-token "$TEST_AUTH_TOKEN"
)
if [[ -n "$DEVICE_ID" ]]; then
  cmd+=(--device-id "$DEVICE_ID")
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
