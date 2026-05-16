#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  agent_ops/deploy/prod/config_release_apply_stage.sh \
    --service <svc> --step <5|25|50|100> \
    --from-image <old> --to-image <new> \
    --from-config <old_cfg> --to-config <new_cfg> \
    --error-rate <float> --p95-ms <int> --redis-error-rate <float>

Behavior:
  1) Update rollout stage state.
  2) Evaluate SLO gate.
  3) On rollback decision, execute config rollback automatically.
EOF
}

SERVICE=""
STEP=""
FROM_IMAGE=""
TO_IMAGE=""
FROM_CONFIG=""
TO_CONFIG=""
ERROR_RATE=""
P95_MS=""
REDIS_ERROR_RATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="${2:-}"; shift 2 ;;
    --step) STEP="${2:-}"; shift 2 ;;
    --from-image) FROM_IMAGE="${2:-}"; shift 2 ;;
    --to-image) TO_IMAGE="${2:-}"; shift 2 ;;
    --from-config) FROM_CONFIG="${2:-}"; shift 2 ;;
    --to-config) TO_CONFIG="${2:-}"; shift 2 ;;
    --error-rate) ERROR_RATE="${2:-}"; shift 2 ;;
    --p95-ms) P95_MS="${2:-}"; shift 2 ;;
    --redis-error-rate) REDIS_ERROR_RATE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

for v in SERVICE STEP FROM_IMAGE TO_IMAGE FROM_CONFIG TO_CONFIG ERROR_RATE P95_MS REDIS_ERROR_RATE; do
  if [[ -z "${!v}" ]]; then
    echo "FAIL: missing required arg $v" >&2
    usage
    exit 2
  fi
done

bash "$ROOT/agent_ops/deploy/prod/config_release_gray_rollout.sh" \
  --service "$SERVICE" \
  --from-image "$FROM_IMAGE" \
  --to-image "$TO_IMAGE" \
  --from-config "$FROM_CONFIG" \
  --to-config "$TO_CONFIG" \
  --step "$STEP"

set +e
gate_output="$(bash "$ROOT/agent_ops/deploy/prod/config_release_slo_gate.sh" \
  --error-rate "$ERROR_RATE" \
  --p95-ms "$P95_MS" \
  --redis-error-rate "$REDIS_ERROR_RATE" 2>&1)"
gate_code=$?
set -e
echo "$gate_output"

case "$gate_code" in
  0)
    echo "OK: stage=$STEP decision=continue service=$SERVICE"
    ;;
  10)
    echo "WARN: stage=$STEP decision=pause service=$SERVICE"
    ;;
  20)
    echo "WARN: stage=$STEP decision=rollback service=$SERVICE -> rolling back to $FROM_CONFIG"
    bash "$ROOT/agent_ops/deploy/prod/config_release_rollback.sh" --service "$SERVICE" --to-config-version "$FROM_CONFIG"
    ;;
  *)
    echo "FAIL: unexpected SLO gate exit code: $gate_code" >&2
    exit "$gate_code"
    ;;
esac
