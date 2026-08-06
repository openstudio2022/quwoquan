#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
RUNTIME_TOPOLOGY="$ROOT/quwoquan_ops/environments/gamma/runtime.yaml"
TARGET="gamma-local"

if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "onboarding-author-impact-api-uat", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi

REPORT="${LOCAL_GAMMA_ONBOARDING_AUTHOR_IMPACT_API_UAT_REPORT:-$QWQ_RUN_ROOT/onboarding_author_impact_api_uat_report.json}"
RELEASE_REPORT="$QWQ_RUN_ROOT/onboarding_author_impact_release_report.json"
READINESS_RECEIPT="${DATA_RELEASE_READINESS_RECEIPT:-}"
SESSION_DEFINES="$(mktemp "${TMPDIR:-/tmp}/qwq-gamma-api-uat-defines.XXXXXX.json")"
chmod 600 "$SESSION_DEFINES"
trap 'rm -f "$SESSION_DEFINES"' EXIT

if [[ ! -f "$RUNTIME_TOPOLOGY" ]]; then
  echo "[local-gamma:onboarding-author-impact-api] GATE_BLOCK: gamma runtime topology is missing" >&2
  exit 2
fi
if [[ -z "$READINESS_RECEIPT" ]]; then
  echo "[local-gamma:onboarding-author-impact-api] GATE_BLOCK: DATA_RELEASE_READINESS_RECEIPT is required" >&2
  exit 2
fi

GATEWAY_BASE_URL="$(python3 - <<'PY'
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology

value = str(
    get_target(load_environment_topology(), "gamma-local")["publicBases"]["api"]
).strip()
if not value:
    raise SystemExit("invalid gamma runtime topology: publicBases.api is empty")
print(value)
PY
)"

FLUTTER_GATEWAY_URL="$GATEWAY_BASE_URL"

mkdir -p "$(dirname "$REPORT")"
health_status=0
release_status=0
api_status=0

if ! python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
  health --target "$TARGET" --scope full; then
  health_status=1
fi

if [[ "$health_status" -eq 0 ]]; then
  if ! python3 "$ROOT/quwoquan_app/scripts/gamma/run_local_gamma_release_consumer_api.py" \
    --release-readiness "$READINESS_RECEIPT" \
    --report "$RELEASE_REPORT"; then
    release_status=1
  fi
fi

if [[ "$health_status" -eq 0 && "$release_status" -eq 0 ]]; then
  if ! PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
    "$GATEWAY_BASE_URL" "$SESSION_DEFINES" <<'PY'
import json
import os
import sys
from pathlib import Path

from quwoquan_ops.cli.lib.local_environment_auth import (
    open_reference_acceptance_session,
)

gateway, output = sys.argv[1:3]
session = open_reference_acceptance_session(
    gateway,
    environment="gamma",
    target_name="gamma-local",
)
path = Path(output)
path.write_text(
    json.dumps(
        {
            "TEST_AUTH_TOKEN": session.access_token,
            "GAMMA_ACCEPTANCE_PERSONA_ID": session.persona_id,
        },
        ensure_ascii=False,
    )
    + "\n",
    encoding="utf-8",
)
os.chmod(path, 0o600)
PY
  then
    api_status=1
  elif ! (
    cd "$ROOT/quwoquan_app"
    flutter test \
      test/api_integration/service/content_service/content/content_behavior_fact/onboarding_interest_gamma__api_integration_test.dart \
      test/api_integration/service/content_service/content/post/author_impact_gamma__api_integration_test.dart \
      "--dart-define-from-file=$SESSION_DEFINES" \
      "--dart-define=GAMMA_GATEWAY_URL=$FLUTTER_GATEWAY_URL" \
      --dart-define=API_CONTRACT_ALLOW_BAD_CERT=true
  ); then
    api_status=1
  fi
fi

status="passed"
if [[ "$health_status" -ne 0 || "$release_status" -ne 0 || "$api_status" -ne 0 ]]; then
  status="failed"
fi

python3 - "$REPORT" "$status" "$RELEASE_REPORT" \
  "$health_status" "$release_status" "$api_status" <<'PY'
import json
import sys
from pathlib import Path

report_path, status, release_report, health, release, api = sys.argv[1:]
Path(report_path).write_text(
    json.dumps(
        {
            "status": status,
            "target": "gamma-local",
            "evidenceClass": "api_integration_remote",
            "cases": {
                "stackHealth": {"exitCode": int(health)},
                "immutableReleaseConsumer": {
                    "exitCode": int(release),
                    "report": release_report,
                },
                "remoteAdapterBlackBox": {"exitCode": int(api)},
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

echo "[local-gamma:onboarding-author-impact-api] report: $REPORT"
echo "[local-gamma:onboarding-author-impact-api] status: $status"
[[ "$status" == "passed" ]]
