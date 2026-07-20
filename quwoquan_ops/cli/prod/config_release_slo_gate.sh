#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
POLICY_FILE="${SLO_POLICY_FILE:-$ROOT/quwoquan_ops/policies/config-release/slo_thresholds.yaml}"

usage() {
  cat <<'EOF'
Usage:
  quwoquan_ops/cli/prod/config_release_slo_gate.sh \
    --error-rate <float> --p95-ms <int> --redis-error-rate <float>

Output:
  decision=continue|pause|rollback
Exit code:
  0=continue, 10=pause, 20=rollback

Thresholds:
  Read only from quwoquan_ops/policies/config-release/slo_thresholds.yaml.
EOF
}

ERROR_RATE=""
P95_MS=""
REDIS_ERROR_RATE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --error-rate) ERROR_RATE="${2:-}"; shift 2 ;;
    --p95-ms) P95_MS="${2:-}"; shift 2 ;;
    --redis-error-rate) REDIS_ERROR_RATE="${2:-}"; shift 2 ;;
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

if [[ ! -s "$POLICY_FILE" ]]; then
  echo "FAIL: SLO policy is missing: $POLICY_FILE" >&2
  exit 2
fi

read -r ER_WARN ER_CRIT P95_WARN P95_CRIT RE_WARN RE_CRIT < <(
  ruby -ryaml -e '
    policy = YAML.load_file(ARGV.fetch(0))
    thresholds = policy.fetch("thresholds")
    puts [
      thresholds.fetch("error_rate").fetch("warn"),
      thresholds.fetch("error_rate").fetch("critical"),
      thresholds.fetch("p95_ms").fetch("warn"),
      thresholds.fetch("p95_ms").fetch("critical"),
      thresholds.fetch("redis_error_rate").fetch("warn"),
      thresholds.fetch("redis_error_rate").fetch("critical"),
    ].join(" ")
  ' "$POLICY_FILE"
)

python3 - "$ERROR_RATE" "$P95_MS" "$REDIS_ERROR_RATE" "$ER_WARN" "$ER_CRIT" "$P95_WARN" "$P95_CRIT" "$RE_WARN" "$RE_CRIT" "$POLICY_FILE" <<'PY'
import sys

er = float(sys.argv[1])
p95 = int(float(sys.argv[2]))
re = float(sys.argv[3])
er_warn, er_crit = float(sys.argv[4]), float(sys.argv[5])
p95_warn, p95_crit = int(float(sys.argv[6])), int(float(sys.argv[7]))
re_warn, re_crit = float(sys.argv[8]), float(sys.argv[9])
policy_file = sys.argv[10]

if er >= er_crit or p95 >= p95_crit or re >= re_crit:
    print(f"decision=rollback policy={policy_file}")
    sys.exit(20)
if er >= er_warn or p95 >= p95_warn or re >= re_warn:
    print(f"decision=pause policy={policy_file}")
    sys.exit(10)
print(f"decision=continue policy={policy_file}")
sys.exit(0)
PY
