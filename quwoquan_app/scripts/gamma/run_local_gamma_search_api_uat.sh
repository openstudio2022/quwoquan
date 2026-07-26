#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
RUNTIME_TOPOLOGY="$ROOT/quwoquan_ops/environments/gamma/runtime.yaml"
TARGET="gamma-local"

if [[ -z "${QWQ_RUN_ROOT:-}" ]]; then
  QWQ_RUN_ROOT="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import env_run_dir
print(env_run_dir("gamma", "search-remote-api-uat", target="gamma-local"))
PY
)"
  export QWQ_RUN_ROOT
fi

REPORT="${LOCAL_GAMMA_SEARCH_API_UAT_REPORT:-$QWQ_RUN_ROOT/search_remote_api_uat_report.json}"
EVIDENCE="$QWQ_RUN_ROOT/search_remote_api_evidence.json"
TAG_FILTER_EVIDENCE="$QWQ_RUN_ROOT/search_tag_filter_evidence.json"
TEST_LOG="$QWQ_RUN_ROOT/search_remote_api_uat.log"
SESSION_DEFINES="$(mktemp "${TMPDIR:-/tmp}/qwq-gamma-search-api-uat.XXXXXX.json")"
chmod 600 "$SESSION_DEFINES"
trap 'rm -f "$SESSION_DEFINES"' EXIT

if [[ ! -f "$RUNTIME_TOPOLOGY" ]]; then
  echo "[local-gamma:search-api] GATE_BLOCK: gamma runtime topology is missing" >&2
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

mkdir -p "$(dirname "$REPORT")"
health_status=0
api_status=0
tag_filter_status=0

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
    json.dumps({"TEST_AUTH_TOKEN": session.access_token}, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
os.chmod(path, 0o600)
PY
  then
    api_status=1
  elif ! (
    cd "$ROOT/quwoquan_app"
    SEARCH_REMOTE_EVIDENCE_PATH="$EVIDENCE" flutter test \
      test/api_integration/cloud/search/search_remote_roundtrip__api_integration_test.dart \
      "--dart-define-from-file=$SESSION_DEFINES" \
      "--dart-define=GAMMA_GATEWAY_URL=$GATEWAY_BASE_URL" \
      --dart-define=GAMMA_GATEWAY_RESOLVE_HOST=127.0.0.1 \
      2>&1 | tee "$TEST_LOG"
  ); then
    api_status=1
  fi
fi

if [[ "$health_status" -eq 0 && "$api_status" -eq 0 ]]; then
  if ! python3 - "$GATEWAY_BASE_URL" "$TAG_FILTER_EVIDENCE" <<'PY'
import json
import socket
import ssl
import sys
import urllib.request

base_url, output_path = sys.argv[1:3]
original_getaddrinfo = socket.getaddrinfo
host = "gamma-api.quwoquan-env.test"

def resolve_local(value, *args, **kwargs):
    return original_getaddrinfo("127.0.0.1" if value == host else value, *args, **kwargs)

socket.getaddrinfo = resolve_local
context = ssl._create_unverified_context()

def search(tags):
    request = urllib.request.Request(
        base_url.rstrip("/") + "/search",
        data=json.dumps(
            {
                "query": "西湖",
                "objectTypes": ["photo"],
                "filters": {"tags": tags},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, context=context, timeout=20) as response:
        return json.load(response)

positive = search(["photography"])
negative = search(["no-such-tag"])
if (
    not positive.get("requestId")
    or not positive.get("hits")
    or positive["hits"][0].get("objectId") != "fixture_photo_001"
    or not negative.get("requestId")
    or negative.get("hits")
):
    raise SystemExit("Gamma tag filter positive/negative assertions failed")

with open(output_path, "w", encoding="utf-8") as output:
    json.dump(
        {
            "schema": "search-tag-filter-remote-evidence-v1",
            "status": "passed",
            "positiveRequestId": positive["requestId"],
            "positiveHitCount": len(positive["hits"]),
            "positiveObjectId": positive["hits"][0]["objectId"],
            "negativeRequestId": negative["requestId"],
            "negativeHitCount": len(negative["hits"]),
        },
        output,
        ensure_ascii=False,
    )
    output.write("\n")
PY
  then
    tag_filter_status=1
  fi
fi

status="passed"
if [[ "$health_status" -ne 0 || "$api_status" -ne 0 || "$tag_filter_status" -ne 0 || ! -s "$EVIDENCE" || ! -s "$TAG_FILTER_EVIDENCE" ]]; then
  status="failed"
fi

python3 - "$REPORT" "$status" "$health_status" "$api_status" "$tag_filter_status" "$EVIDENCE" "$TAG_FILTER_EVIDENCE" "$TEST_LOG" <<'PY'
import json
import sys
from pathlib import Path

report_path, status, health, api, tag_filter, evidence_path, tag_filter_path, log_path = sys.argv[1:]
evidence = {}
path = Path(evidence_path)
if path.is_file():
    evidence = json.loads(path.read_text(encoding="utf-8"))
tag_filter_evidence = {}
path = Path(tag_filter_path)
if path.is_file():
    tag_filter_evidence = json.loads(path.read_text(encoding="utf-8"))
Path(report_path).write_text(
    json.dumps(
        {
            "schema": "search-remote-api-uat-report-v1",
            "status": status,
            "target": "gamma-local",
            "evidenceClass": "api_integration_remote",
            "cases": {
                "stackHealth": {"exitCode": int(health)},
                "searchAndFeedbackRoundtrip": {
                    "exitCode": int(api),
                    "evidence": evidence,
                    "logPath": log_path,
                },
                "tagFilterPositiveAndNegative": {
                    "exitCode": int(tag_filter),
                    "evidence": tag_filter_evidence,
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

echo "[local-gamma:search-api] report: $REPORT"
echo "[local-gamma:search-api] status: $status"
[[ "$status" == "passed" ]]
