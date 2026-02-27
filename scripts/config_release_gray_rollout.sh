#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  scripts/config_release_gray_rollout.sh --service <svc> \
    --from-image <old> --to-image <new> \
    --from-config <old_cfg> --to-config <new_cfg> \
    --step <5|25|50|100>

Behavior:
  - Validates rollout step sequence.
  - Ensures target config version file exists.
  - Writes rollout state to .release-state/<service>.state.
EOF
}

SERVICE=""
FROM_IMAGE=""
TO_IMAGE=""
FROM_CONFIG=""
TO_CONFIG=""
STEP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="${2:-}"; shift 2 ;;
    --from-image) FROM_IMAGE="${2:-}"; shift 2 ;;
    --to-image) TO_IMAGE="${2:-}"; shift 2 ;;
    --from-config) FROM_CONFIG="${2:-}"; shift 2 ;;
    --to-config) TO_CONFIG="${2:-}"; shift 2 ;;
    --step) STEP="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

for v in SERVICE FROM_IMAGE TO_IMAGE FROM_CONFIG TO_CONFIG STEP; do
  if [[ -z "${!v}" ]]; then
    echo "FAIL: missing required arg ${v}" >&2
    usage
    exit 2
  fi
done

case "$STEP" in
  5|25|50|100) ;;
  *) echo "FAIL: --step must be one of 5|25|50|100" >&2; exit 2 ;;
esac

cfg_file="$ROOT/releases/config/$SERVICE/$TO_CONFIG.yaml"
if [[ ! -f "$cfg_file" ]]; then
  echo "FAIL: target config version file not found: $cfg_file" >&2
  exit 1
fi

state_dir="$ROOT/.release-state"
mkdir -p "$state_dir"
state_file="$state_dir/$SERVICE.state"
audit_file="$state_dir/$SERVICE.audit.log"

prev_step=0
if [[ -f "$state_file" ]]; then
  prev_step="$(awk -F= '/^step=/{print $2}' "$state_file" || true)"
  prev_step="${prev_step:-0}"
fi

if [[ "$prev_step" -gt "$STEP" ]]; then
  echo "FAIL: rollout step cannot go backwards (prev=$prev_step, next=$STEP)" >&2
  exit 1
fi

cat >"$state_file" <<EOF
service=$SERVICE
from_image=$FROM_IMAGE
to_image=$TO_IMAGE
from_config=$FROM_CONFIG
to_config=$TO_CONFIG
step=$STEP
updated_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") rollout service=$SERVICE step=$STEP from_image=$FROM_IMAGE to_image=$TO_IMAGE from_config=$FROM_CONFIG to_config=$TO_CONFIG" >>"$audit_file"

echo "OK: rollout state updated: $state_file (step=$STEP)"
