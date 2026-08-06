#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
RUNTIME_TOPOLOGY="$ROOT/quwoquan_ops/environments/gamma/runtime.yaml"
TARGET="gamma-local"

if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "assistant-learning-remote-api-uat", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi

REPORT="${LOCAL_GAMMA_ASSISTANT_LEARNING_API_UAT_REPORT:-$QWQ_RUN_ROOT/assistant_learning_remote_api_uat_report.json}"
EVIDENCE="$QWQ_RUN_ROOT/assistant_learning_remote_api_evidence.json"
RELAY_EVIDENCE="$QWQ_RUN_ROOT/assistant_learning_relay_evidence.json"
TEST_LOG="$QWQ_RUN_ROOT/assistant_learning_remote_api_uat.log"
SESSION_DEFINES="$(mktemp "${TMPDIR:-/tmp}/qwq-gamma-assistant-learning-api-uat.XXXXXX.json")"
chmod 600 "$SESSION_DEFINES"
trap 'rm -f "$SESSION_DEFINES"' EXIT

if [[ ! -f "$RUNTIME_TOPOLOGY" ]]; then
  echo "[local-gamma:assistant-learning-api] GATE_BLOCK: gamma runtime topology is missing" >&2
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
    ASSISTANT_LEARNING_REMOTE_EVIDENCE_PATH="$EVIDENCE" flutter test \
      test/api_integration/service/assistant_service/assistant/assistant_learning_fact/assistant_learning_remote_roundtrip__api_integration_test.dart \
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
event_id = str(api_evidence.get("eventId") or "").strip()
if not event_id:
    raise SystemExit("Assistant learning API evidence has no eventId")

matched_ref = ""
for _ in range(40):
    redis_result = subprocess.run(
        [
            "docker",
            "exec",
            "quwoquan_service-redis-1",
            "redis-cli",
            "--json",
            "XRANGE",
            "events.assistant.learning_facts",
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
        raise SystemExit("read Assistant learning stream failed")
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
        if fields.get("aggregateId") == event_id:
            matched_ref = str(entry[0])
            break
    if matched_ref:
        break
    time.sleep(0.25)
if not matched_ref:
    raise SystemExit("Assistant learning event is absent from durable stream")

mongo_script = """
const eventId = process.env.QWQ_EVENT_ID;
const document = db.getSiblingDB('quwoquan_assistant')
  .assistant_learning_fact_outbox.findOne({
    'payload.eventId': eventId,
    publishedAt: {$exists: true},
  });
print(JSON.stringify({
  found: document !== null,
  publishedRef: document ? String(document.publishedRef || '') : '',
}));
"""
outbox = {}
for _ in range(40):
    mongo_result = subprocess.run(
        [
            "docker",
            "exec",
            "-e",
            f"QWQ_EVENT_ID={event_id}",
            "quwoquan_service-mongodb-1",
            "mongosh",
            "--quiet",
            "--eval",
            mongo_script,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if mongo_result.returncode != 0:
        raise SystemExit("read Assistant learning outbox failed")
    lines = [line for line in mongo_result.stdout.splitlines() if line.strip()]
    outbox = json.loads(lines[-1]) if lines else {}
    if outbox.get("found") and str(outbox.get("publishedRef") or "").strip():
        break
    time.sleep(0.25)
if not outbox.get("found") or not str(outbox.get("publishedRef") or "").strip():
    raise SystemExit("Assistant learning outbox is not marked published")

relay_evidence_path.write_text(
    json.dumps(
        {
            "schema": "assistant-learning-relay-evidence",
            "status": "passed",
            "eventId": event_id,
            "stream": "events.assistant.learning_facts",
            "streamRef": matched_ref,
            "outboxPublishedRef": outbox["publishedRef"],
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
            "schema": "assistant-learning-remote-api-uat-report",
            "status": status,
            "target": "gamma-local",
            "evidenceClass": "api_integration_remote",
            "cases": {
                "stackHealth": {"exitCode": int(health)},
                "conversationRunAndLearningFactRoundtrip": {
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

echo "[local-gamma:assistant-learning-api] report: $REPORT"
echo "[local-gamma:assistant-learning-api] status: $status"
[[ "$status" == "passed" ]]
