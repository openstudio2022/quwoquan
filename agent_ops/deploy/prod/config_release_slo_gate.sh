#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  agent_ops/deploy/prod/config_release_slo_gate.sh \
    --error-rate <float> --p95-ms <int> --redis-error-rate <float> \
    [--error-rate-warn <float>] [--error-rate-crit <float>] \
    [--p95-warn-ms <int>] [--p95-crit-ms <int>] \
    [--redis-error-warn <float>] [--redis-error-crit <float>]

Output:
  decision=continue|pause|rollback
Exit code:
  0=continue, 10=pause, 20=rollback
EOF
}

ERROR_RATE=""
P95_MS=""
REDIS_ERROR_RATE=""
ER_WARN="0.01"
ER_CRIT="0.03"
P95_WARN="300"
P95_CRIT="600"
RE_WARN="0.01"
RE_CRIT="0.03"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --error-rate) ERROR_RATE="${2:-}"; shift 2 ;;
    --p95-ms) P95_MS="${2:-}"; shift 2 ;;
    --redis-error-rate) REDIS_ERROR_RATE="${2:-}"; shift 2 ;;
    --error-rate-warn) ER_WARN="${2:-}"; shift 2 ;;
    --error-rate-crit) ER_CRIT="${2:-}"; shift 2 ;;
    --p95-warn-ms) P95_WARN="${2:-}"; shift 2 ;;
    --p95-crit-ms) P95_CRIT="${2:-}"; shift 2 ;;
    --redis-error-warn) RE_WARN="${2:-}"; shift 2 ;;
    --redis-error-crit) RE_CRIT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

for v in ERROR_RATE P95_MS REDIS_ERROR_RATE; do
  if [[ -z "${!v}" ]]; then
    echo "FAIL: missing required arg $v" >&2
    usage
    exit 2
  fi
done

python3 - "$ERROR_RATE" "$P95_MS" "$REDIS_ERROR_RATE" "$ER_WARN" "$ER_CRIT" "$P95_WARN" "$P95_CRIT" "$RE_WARN" "$RE_CRIT" <<'PY'
import sys

er = float(sys.argv[1])
p95 = int(float(sys.argv[2]))
re = float(sys.argv[3])
er_warn, er_crit = float(sys.argv[4]), float(sys.argv[5])
p95_warn, p95_crit = int(float(sys.argv[6])), int(float(sys.argv[7]))
re_warn, re_crit = float(sys.argv[8]), float(sys.argv[9])

if er >= er_crit or p95 >= p95_crit or re >= re_crit:
    print("decision=rollback")
    sys.exit(20)
if er >= er_warn or p95 >= p95_warn or re >= re_warn:
    print("decision=pause")
    sys.exit(10)
print("decision=continue")
sys.exit(0)
PY
