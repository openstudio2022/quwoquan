#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
RUNTIME_TOPOLOGY="$ROOT/quwoquan_ops/environments/gamma/runtime.yaml"
TARGET="gamma-local"

if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "profile-proposal-remote-api-uat", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi

REPORT="${LOCAL_GAMMA_PROFILE_PROPOSAL_API_UAT_REPORT:-$QWQ_RUN_ROOT/profile_proposal_remote_api_uat_report.json}"
EVIDENCE="$QWQ_RUN_ROOT/profile_proposal_remote_api_evidence.json"
RELAY_EVIDENCE="$QWQ_RUN_ROOT/profile_proposal_relay_evidence.json"
TEST_LOG="$QWQ_RUN_ROOT/profile_proposal_remote_api_uat.log"
SESSION_DEFINES="$(mktemp "${TMPDIR:-/tmp}/qwq-gamma-profile-proposal-api-uat.XXXXXX.json")"
chmod 600 "$SESSION_DEFINES"
trap 'rm -f "$SESSION_DEFINES"' EXIT

if [[ ! -f "$RUNTIME_TOPOLOGY" ]]; then
  echo "[local-gamma:profile-proposal-api] GATE_BLOCK: gamma runtime topology is missing" >&2
  exit 2
fi

GATEWAY_BASE_URL="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

value = str(
    get_target(load_environment_topology(), "gamma-local")["publicBases"]["api"]
).strip()
if not value:
    raise SystemExit("resolved gamma-local publicBases.api is empty")
print(value)
PY
)"

mkdir -p "$(dirname "$REPORT")"
health_status=0
api_status=0
relay_status=0

if ! python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
  health --target "$TARGET" --scope full; then
  health_status=1
fi

if [[ "$health_status" -eq 0 ]]; then
  if ! PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
    "$GATEWAY_BASE_URL" "$SESSION_DEFINES" <<'PY'
import json
import os
import sys
from pathlib import Path

from quwoquan_ops.cli.lib.local_environment_auth import (
    open_local_acceptance_session,
    resolve_running_local_deployment_work_root,
)

gateway, output = sys.argv[1:3]
session_kwargs = {
    "environment": "gamma",
    "target_name": "gamma-local",
}
deployment_work_root = resolve_running_local_deployment_work_root("gamma-local")
if deployment_work_root is not None:
    session_kwargs["deployment_work_root"] = deployment_work_root
session = open_local_acceptance_session(gateway, **session_kwargs)
path = Path(output)
path.write_text(
    json.dumps(
        {
            "TEST_AUTH_TOKEN": session.access_token,
            "TEST_PERSONA_ID": session.persona_id,
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
    PROFILE_PROPOSAL_REMOTE_EVIDENCE_PATH="$EVIDENCE" flutter test \
      test/api_integration/cloud/user/profile_update_proposal_remote_roundtrip__api_integration_test.dart \
      "--dart-define-from-file=$SESSION_DEFINES" \
      --dart-define=APP_RUNTIME_ENV=gamma \
      "--dart-define=CLOUD_GATEWAY_BASE_URL=$GATEWAY_BASE_URL" \
      --dart-define=GAMMA_GATEWAY_RESOLVE_HOST=127.0.0.1 \
      2>&1 | tee "$TEST_LOG"
  ); then
    api_status=1
  fi
fi

if [[ "$api_status" -eq 0 ]]; then
  if ! python3 - "$EVIDENCE" "$RELAY_EVIDENCE" <<'PY'
import json
import subprocess
import sys
import time
from pathlib import Path

api_evidence_path, relay_evidence_path = map(Path, sys.argv[1:])
api_evidence = json.loads(api_evidence_path.read_text(encoding="utf-8"))
proposal_id = str(api_evidence.get("proposalId") or "").strip()
if not proposal_id:
    raise SystemExit("Profile proposal API evidence has no proposalId")

matched_ref = ""
matched_event = ""
for _ in range(40):
    redis_result = subprocess.run(
        [
            "docker",
            "exec",
            "quwoquan_service-redis-1",
            "redis-cli",
            "--json",
            "XRANGE",
            "events.user.profile_update_proposal",
            "-",
            "+",
            "COUNT",
            "1000",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if redis_result.returncode != 0:
        raise SystemExit("read ProfileUpdateProposal event stream failed")
    for entry in json.loads(redis_result.stdout):
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        raw_fields = entry[1]
        if not isinstance(raw_fields, list) or len(raw_fields) % 2:
            continue
        fields = {
            str(raw_fields[index]): str(raw_fields[index + 1])
            for index in range(0, len(raw_fields), 2)
        }
        if (
            fields.get("proposalId") == proposal_id
            and fields.get("eventName") == "ProfileUpdateProposalRolledBack"
        ):
            matched_ref = str(entry[0])
            matched_event = str(fields.get("eventId") or "")
            break
    if matched_ref:
        break
    time.sleep(0.25)
if not matched_ref or not matched_event:
    raise SystemExit("rolled-back ProfileUpdateProposal event is absent from stream")

published_count = 0
for _ in range(40):
    sql = (
        "SELECT count(*) FROM profile_update_proposals_outbox "
        "WHERE aggregate_id = :'proposal_id' AND published_at IS NOT NULL;"
    )
    postgres_result = subprocess.run(
        [
            "docker",
            "exec",
            "-e",
            f"PGOPTIONS=-c qwq.proposal_id={proposal_id}",
            "quwoquan_service-postgres-1",
            "psql",
            "-U",
            "quwoquan",
            "-d",
            "quwoquan",
            "-tAc",
            sql.replace(
                ":'proposal_id'",
                "current_setting('qwq.proposal_id')",
            ),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if postgres_result.returncode != 0:
        raise SystemExit("read ProfileUpdateProposal outbox failed")
    published_count = int(postgres_result.stdout.strip() or "0")
    if published_count > 0:
        break
    time.sleep(0.25)
if published_count <= 0:
    raise SystemExit("ProfileUpdateProposal outbox is not marked published")

relay_evidence_path.write_text(
    json.dumps(
        {
            "schema": "profile-proposal-relay-evidence",
            "status": "passed",
            "proposalId": proposal_id,
            "stream": "events.user.profile_update_proposal",
            "rolledBackEventId": matched_event,
            "streamRef": matched_ref,
            "publishedOutboxRows": published_count,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY
  then
    relay_status=1
  fi
fi

status="passed"
if [[ "$health_status" -ne 0 || "$api_status" -ne 0 || "$relay_status" -ne 0 || ! -s "$EVIDENCE" || ! -s "$RELAY_EVIDENCE" ]]; then
  status="failed"
fi

python3 - "$REPORT" "$status" "$health_status" "$api_status" "$relay_status" "$EVIDENCE" "$RELAY_EVIDENCE" "$TEST_LOG" <<'PY'
import json
import sys
from pathlib import Path

report_path, status, health, api, relay, evidence_path, relay_path, log_path = sys.argv[1:]
evidence = {}
path = Path(evidence_path)
if path.is_file():
    evidence = json.loads(path.read_text(encoding="utf-8"))
relay_evidence = {}
path = Path(relay_path)
if path.is_file():
    relay_evidence = json.loads(path.read_text(encoding="utf-8"))
Path(report_path).write_text(
    json.dumps(
        {
            "schema": "profile-proposal-remote-api-uat-report",
            "status": status,
            "target": "gamma-local",
            "evidenceClass": "api_integration_remote",
            "cases": {
                "stackHealth": {"exitCode": int(health)},
                "profileProposalApplyRollbackRoundtrip": {
                    "exitCode": int(api),
                    "evidence": evidence,
                    "logPath": log_path,
                },
                "durableOutboxRelay": {
                    "exitCode": int(relay),
                    "evidence": relay_evidence,
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

echo "[local-gamma:profile-proposal-api] report: $REPORT"
echo "[local-gamma:profile-proposal-api] status: $status"
[[ "$status" == "passed" ]]
