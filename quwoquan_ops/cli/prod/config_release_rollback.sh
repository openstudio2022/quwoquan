#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"

usage() {
  cat <<'EOF'
Usage:
  quwoquan_ops/cli/prod/config_release_rollback.sh --service <svc> --to-config-version <sha256:digest>

Behavior:
  - Records an idempotent rollback request in the external runtime state directory.
  - Never edits service deployment or configuration truth sources.
EOF
}

SERVICE=""
TARGET_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="${2:-}"; shift 2 ;;
    --to-config-version) TARGET_VERSION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$SERVICE" || -z "$TARGET_VERSION" ]]; then
  echo "FAIL: --service and --to-config-version are required" >&2
  usage
  exit 2
fi

if [[ ! "$TARGET_VERSION" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "FAIL: --to-config-version must be a sha256 digest" >&2
  exit 1
fi

state_dir="$QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state"
mkdir -p "$state_dir"
lock_dir="$state_dir/$SERVICE.rollback.lock"
audit_file="$state_dir/$SERVICE.audit.log"

if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "FAIL: rollback lock busy for service=$SERVICE (another rollback in progress)" >&2
  exit 1
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

request_file="$state_dir/$SERVICE.rollback.request"
printf 'service=%s\ntarget_config=%s\nrequested_at=%s\n' \
  "$SERVICE" "$TARGET_VERSION" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" >"$request_file"
echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") rollback-request service=$SERVICE target_config=$TARGET_VERSION" >>"$audit_file"
echo "OK: rollback request recorded: $request_file"
