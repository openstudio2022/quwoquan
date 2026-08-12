#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  quwoquan_ops/cli/prod/config_release_apply_stage.sh \
    --service <svc> --step <0|5|20|50|100> \
    --error-rate <float> --p95-ms <int> --redis-error-rate <float>

Behavior:
  Evaluate the live SLO values supplied by stackctl. Release state and rollback
  are committed only by stackctl's locked CAS transaction.
EOF
}

SERVICE=""
STEP=""
ERROR_RATE=""
P95_MS=""
REDIS_ERROR_RATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="${2:-}"; shift 2 ;;
    --step) STEP="${2:-}"; shift 2 ;;
    --error-rate) ERROR_RATE="${2:-}"; shift 2 ;;
    --p95-ms) P95_MS="${2:-}"; shift 2 ;;
    --redis-error-rate) REDIS_ERROR_RATE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

for v in SERVICE STEP ERROR_RATE P95_MS REDIS_ERROR_RATE; do
  if [[ -z "${!v}" ]]; then
    echo "FAIL: missing required arg $v" >&2
    usage
    exit 2
  fi
done

set +e
gate_output="$(bash "$ROOT/quwoquan_ops/cli/prod/config_release_slo_gate.sh" \
  --error-rate "$ERROR_RATE" \
  --p95-ms "$P95_MS" \
  --redis-error-rate "$REDIS_ERROR_RATE" 2>&1)"
gate_code=$?
set -e
echo "$gate_output"

case "$gate_code" in
  0)
    echo "OK: stage=$STEP decision=continue service=$SERVICE"
    exit 0
    ;;
  10)
    echo "WARN: stage=$STEP decision=pause service=$SERVICE"
    exit 10
    ;;
  20)
    echo "WARN: stage=$STEP decision=rollback service=$SERVICE"
    exit 20
    ;;
  *)
    echo "FAIL: unexpected SLO gate exit code: $gate_code" >&2
    exit "$gate_code"
    ;;
esac
