#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
RUNTIME_TOPOLOGY="$ROOT/quwoquan_ops/environments/gamma/runtime.yaml"
TARGET="gamma-local"
READINESS_RECEIPT="${DATA_RELEASE_READINESS_RECEIPT:-}"

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
if [[ -z "$READINESS_RECEIPT" ]]; then
  echo "[local-gamma:search-api] GATE_BLOCK: DATA_RELEASE_READINESS_RECEIPT is required" >&2
  exit 2
fi
if ! PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
  "$READINESS_RECEIPT" <<'PY'
import sys

from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError,
    load_release_content_identity,
    resolve_readiness_path,
)

try:
    load_release_content_identity(
        resolve_readiness_path(sys.argv[1]),
        expected_environment="gamma",
    )
except (ReleaseVideoDeliveryError, ValueError) as exc:
    raise SystemExit(f"GATE_BLOCK: {exc}") from exc
PY
then
  echo "[local-gamma:search-api] GATE_BLOCK: canonical Data readiness receipt is invalid" >&2
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
  if ! PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
    "$GATEWAY_BASE_URL" "$TAG_FILTER_EVIDENCE" "$READINESS_RECEIPT" <<'PY'
import json
import sys
import urllib.request

from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError,
    load_release_content_identity,
    resolve_readiness_path,
)

base_url, output_path, readiness_value = sys.argv[1:4]
try:
    identity = load_release_content_identity(
        resolve_readiness_path(readiness_value),
        expected_environment="gamma",
    )
except (ReleaseVideoDeliveryError, ValueError) as exc:
    raise SystemExit(f"GATE_BLOCK: {exc}") from exc
image_post_ids = {
    str(binding.get("postId") or "").strip()
    for binding in identity["postBindings"]
    if binding.get("contentType") == "image"
    and str(binding.get("postId") or "").strip()
}
if not image_post_ids:
    raise SystemExit(
        "GATE_BLOCK: canonical Data import receipt has no release-bound image postId"
    )
tag_to_image_posts = {}
for post_id in sorted(image_post_ids):
    for tag_ref in identity["postTagRefs"].get(post_id) or []:
        tag_to_image_posts.setdefault(str(tag_ref), set()).add(post_id)
if not tag_to_image_posts:
    raise SystemExit(
        "GATE_BLOCK: canonical Data payload has no tag bound to a release image post"
    )
positive_tag = next(
    (value for value in sorted(tag_to_image_posts) if "摄影" in value),
    sorted(tag_to_image_posts)[0],
)
expected_object_ids = tag_to_image_posts[positive_tag]

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
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)

positive = search([positive_tag])
negative = search(["__qwq_missing_release_tag__"])
positive_hits = positive.get("hits")
positive_hit_ids = {
    str(hit.get("objectId") or "").strip()
    for hit in positive_hits or []
    if isinstance(hit, dict) and str(hit.get("objectId") or "").strip()
}
matched_object_ids = sorted(positive_hit_ids & expected_object_ids)
if (
    not positive.get("requestId")
    or not isinstance(positive_hits, list)
    or not matched_object_ids
    or not negative.get("requestId")
    or negative.get("hits")
):
    raise SystemExit(
        "Gamma release-bound tag filter positive/negative assertions failed"
    )

with open(output_path, "w", encoding="utf-8") as output:
    json.dump(
        {
            "schema": "search-tag-filter-remote-evidence",
            "status": "passed",
            "releaseId": identity["releaseId"],
            "manifestDigest": identity["manifestDigest"],
            "importRunId": identity["importRunId"],
            "verifyRunId": identity["verifyRunId"],
            "readinessReceiptRef": identity["readinessReceiptRef"],
            "positiveTagRef": positive_tag,
            "positiveRequestId": positive["requestId"],
            "positiveHitCount": len(positive_hits),
            "expectedObjectIds": sorted(expected_object_ids),
            "matchedObjectIds": matched_object_ids,
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
            "schema": "search-remote-api-uat-report",
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
