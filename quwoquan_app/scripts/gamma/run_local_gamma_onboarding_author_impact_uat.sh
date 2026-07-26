#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
DEVICE_ID=""
PLATFORM="all"

usage() {
  cat <<'USAGE'
Usage: quwoquan_app/scripts/gamma/run_local_gamma_onboarding_author_impact_uat.sh --device-id <id> [options]

Runs the device-independent Gamma API evidence first, then the real Patrol
interest-onboarding and AuthorImpact profile journeys on the requested device.

Options:
  --device-id <id>  Required Android/iOS device identifier for Patrol.
  --platform <name> android / ios / all (default: all).
  --help            Print this usage.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device-id) DEVICE_ID="${2:-}"; shift 2 ;;
    --platform) PLATFORM="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$DEVICE_ID" ]]; then
  echo "[local-gamma:onboarding-author-impact] GATE_BLOCK: --device-id is required for Patrol UAT" >&2
  exit 2
fi

if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "onboarding-author-impact-uat", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi

REPORT="${LOCAL_GAMMA_ONBOARDING_AUTHOR_IMPACT_UAT_REPORT:-$QWQ_RUN_ROOT/onboarding_author_impact_uat_report.json}"
API_REPORT="$QWQ_RUN_ROOT/onboarding_author_impact_api_uat_report.json"
ONBOARDING_PATROL_REPORT="$QWQ_RUN_ROOT/onboarding_patrol_report.json"
IMPACT_PATROL_REPORT="$QWQ_RUN_ROOT/author_impact_patrol_report.json"
mkdir -p "$(dirname "$REPORT")"

api_status=0
onboarding_patrol_status=0
impact_patrol_status=0

if ! LOCAL_GAMMA_ONBOARDING_AUTHOR_IMPACT_API_UAT_REPORT="$API_REPORT" \
  bash "$ROOT/quwoquan_app/scripts/gamma/run_local_gamma_onboarding_author_impact_api_uat.sh"; then
  api_status=1
fi

if [[ "$api_status" -eq 0 ]]; then
  if ! bash "$ROOT/quwoquan_app/scripts/gamma/run_local_gamma_t4.sh" \
    --device-id "$DEVICE_ID" \
    --platform "$PLATFORM" \
    --target test/user_acceptance/patrol/discovery/interest_onboarding__user_acceptance_test.dart \
    --report "$ONBOARDING_PATROL_REPORT"; then
    onboarding_patrol_status=1
  fi
  if ! bash "$ROOT/quwoquan_app/scripts/gamma/run_local_gamma_t4.sh" \
    --device-id "$DEVICE_ID" \
    --platform "$PLATFORM" \
    --target test/user_acceptance/patrol/user/profile_journey__user_acceptance_test.dart \
    --report "$IMPACT_PATROL_REPORT"; then
    impact_patrol_status=1
  fi
fi

status="passed"
if [[ "$api_status" -ne 0 \
   || "$onboarding_patrol_status" -ne 0 \
   || "$impact_patrol_status" -ne 0 ]]; then
  status="failed"
fi

python3 - "$REPORT" "$status" "$API_REPORT" \
  "$ONBOARDING_PATROL_REPORT" "$IMPACT_PATROL_REPORT" \
  "$api_status" "$onboarding_patrol_status" "$impact_patrol_status" <<'PY'
import json
import sys
from pathlib import Path

(
    report_path,
    status,
    api_report,
    onboarding_report,
    impact_report,
    api,
    onboarding,
    impact,
) = sys.argv[1:]
Path(report_path).write_text(
    json.dumps(
        {
            "status": status,
            "target": "gamma-local",
            "evidenceClass": "user_acceptance_remote",
            "cases": {
                "apiIntegration": {
                    "exitCode": int(api),
                    "report": api_report,
                },
                "patrolOnboardingJourney": {
                    "exitCode": int(onboarding),
                    "report": onboarding_report,
                },
                "patrolAuthorImpactJourney": {
                    "exitCode": int(impact),
                    "report": impact_report,
                },
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

echo "[local-gamma:onboarding-author-impact] report: $REPORT"
echo "[local-gamma:onboarding-author-impact] status: $status"
[[ "$status" == "passed" ]]
