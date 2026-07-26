#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
REUSE_STACK=0

usage() {
  cat <<'USAGE'
Usage: quwoquan_ops/cli/gamma/run_reliabletask_gamma_api_integration.sh [--reuse-stack]

Starts (or reuses) the canonical Gamma-local stack through stackctl, resolves
MongoDB/Redis from the Gamma port profile, and runs the real ReliableTask
Mongo+Redis API-integration suite with isolated test databases.

Options:
  --reuse-stack  Require an already running gamma-local stack instead of
                 calling `stackctl up --env gamma --skip-app`.
  --help         Print this usage.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reuse-stack) REUSE_STACK=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "reliabletask-api-integration", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi

REPORT="${GAMMA_RELIABLETASK_API_INTEGRATION_REPORT:-$QWQ_RUN_ROOT/reliabletask_api_integration_report.json}"
FLEET_REPORT="$QWQ_RUN_ROOT/reliabletask_data_content_fleet_report.json"
mkdir -p "$(dirname "$REPORT")"

if [[ "$REUSE_STACK" -eq 0 ]]; then
  python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
    up --env gamma --skip-app
fi
python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
  health --target gamma-local --scope full

port_profile="$(python3 "$ROOT/quwoquan_ops/cli/print_local_port_profile.py" \
  --profile gamma-local --format json)"
read -r mongo_port redis_port < <(python3 - <<'PY' "$port_profile"
import json
import sys

profile = json.loads(sys.argv[1])
ports = profile["ports"]
print(ports["mongodb"], ports["redis"])
PY
)

data_python="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -B - <<'PY'
from quwoquan_data.scripts.core.python_environment import resolve_data_agent_python

candidate = resolve_data_agent_python()
if candidate is not None:
    print(candidate)
PY
)"
if [[ -z "$data_python" ]]; then
  echo "[gamma:reliabletask-api-integration] preparing disposable data runtime"
  PYTHONDONTWRITEBYTECODE=1 python3 -B "$ROOT/quwoquan_data/scripts/cli.py" \
    task preflight
  data_python="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -B - <<'PY'
from quwoquan_data.scripts.core.python_environment import resolve_data_agent_python

candidate = resolve_data_agent_python()
if candidate is None:
    raise SystemExit(
        "GATE_BLOCK: task preflight completed without a usable "
        "quwoquan-data Python runtime"
    )
print(candidate)
PY
)"
fi

mongo_uri="mongodb://127.0.0.1:${mongo_port}/?directConnection=true"
redis_addr="127.0.0.1:${redis_port}"

set +e
TEST_REPO_ROOT="$ROOT" \
TEST_QWQ_DATA_PYTHON="$data_python" \
TEST_MONGO_URI="$mongo_uri" \
TEST_REDIS_ADDR="$redis_addr" \
QWQ_RELIABLETASK_REPORT_OUT="$FLEET_REPORT" \
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}" \
make -C "$ROOT/quwoquan_service" test-runtime-api-integration
test_status=$?
set -e

python3 - "$REPORT" "$test_status" "$FLEET_REPORT" <<'PY'
import json
import sys
from pathlib import Path

report_path, exit_code, fleet_report = sys.argv[1:]
Path(report_path).write_text(
    json.dumps(
        {
            "status": "passed" if int(exit_code) == 0 else "failed",
            "target": "gamma-local",
            "execution": "stackctl",
            "testCommand": "make -C quwoquan_service test-runtime-api-integration",
            "fleetReport": fleet_report,
            "exitCode": int(exit_code),
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

echo "[gamma:reliabletask-api-integration] report: $REPORT"
exit "$test_status"
