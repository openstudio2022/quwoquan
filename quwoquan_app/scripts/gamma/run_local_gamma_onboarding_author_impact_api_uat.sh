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
SEED_REPORT="$QWQ_RUN_ROOT/onboarding_author_impact_seed_report.json"
SESSION_DEFINES="$(mktemp "${TMPDIR:-/tmp}/qwq-gamma-api-uat-defines.XXXXXX.json")"
chmod 600 "$SESSION_DEFINES"
trap 'rm -f "$SESSION_DEFINES"' EXIT

if [[ ! -f "$RUNTIME_TOPOLOGY" ]]; then
  echo "[local-gamma:onboarding-author-impact-api] GATE_BLOCK: gamma runtime topology is missing" >&2
  exit 2
fi

GATEWAY_BASE_URL="$(python3 - "$RUNTIME_TOPOLOGY" <<'PY'
import json
import sys
from pathlib import Path

try:
    runtime = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    value = str(runtime["publicBases"]["api"]).strip()
except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid gamma runtime topology: {exc}")
if not value:
    raise SystemExit("invalid gamma runtime topology: publicBases.api is empty")
print(value)
PY
)"

FLUTTER_GATEWAY_URL="$(python3 - "$GATEWAY_BASE_URL" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

parts = urlsplit(sys.argv[1].strip())
host = parts.hostname or ""
if host.endswith(".quwoquan-env.test"):
    host = host.removesuffix(".quwoquan-env.test") + ".localhost"
port = f":{parts.port}" if parts.port else ""
print(urlunsplit((parts.scheme, host + port, parts.path, parts.query, parts.fragment)))
PY
)"

mkdir -p "$(dirname "$REPORT")"
health_status=0
seed_status=0
api_status=0

if ! python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
  health --target "$TARGET" --scope full; then
  health_status=1
fi

if [[ "$health_status" -eq 0 ]]; then
  if ! python3 "$ROOT/quwoquan_app/scripts/gamma/run_local_gamma_t3.py" \
    --seed-only \
    --report "$SEED_REPORT"; then
    seed_status=1
  fi
fi

if [[ "$health_status" -eq 0 && "$seed_status" -eq 0 ]]; then
  if ! PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
    "$GATEWAY_BASE_URL" "$SESSION_DEFINES" <<'PY'
import json
import os
import sys
from pathlib import Path

from quwoquan_ops.cli.lib.local_environment_auth import open_local_acceptance_session

gateway, output = sys.argv[1:3]
session = open_local_acceptance_session(
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
      test/api_integration/cloud/content/onboarding_author_impact_gamma__api_integration_test.dart \
      "--dart-define-from-file=$SESSION_DEFINES" \
      "--dart-define=GAMMA_GATEWAY_URL=$FLUTTER_GATEWAY_URL" \
      --dart-define=API_CONTRACT_ALLOW_BAD_CERT=true
  ); then
    api_status=1
  fi
fi

status="passed"
if [[ "$health_status" -ne 0 || "$seed_status" -ne 0 || "$api_status" -ne 0 ]]; then
  status="failed"
fi

python3 - "$REPORT" "$status" "$SEED_REPORT" \
  "$health_status" "$seed_status" "$api_status" <<'PY'
import json
import sys
from pathlib import Path

report_path, status, seed_report, health, seed, api = sys.argv[1:]
Path(report_path).write_text(
    json.dumps(
        {
            "status": status,
            "target": "gamma-local",
            "evidenceClass": "api_integration_remote",
            "cases": {
                "stackHealth": {"exitCode": int(health)},
                "seedCanonicalEvidence": {
                    "exitCode": int(seed),
                    "report": seed_report,
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
