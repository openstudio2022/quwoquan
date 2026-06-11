#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

TARGET="${VERIFY_DEPLOY_TARGET:-gamma-hosted}"
MODE="${VERIFY_DEPLOY_MODE:-restart}"
STAGE="${VERIFY_DEPLOY_STAGE:-prod}"
RUNS="${VERIFY_DEPLOY_RUNS:-1}"
MAX_SECONDS="${VERIFY_DEPLOY_MAX_SECONDS:-300}"
BASE_URL="${VERIFY_DEPLOY_BASE_URL:-}"
PRODUCT_OPS_BASE_URL="${VERIFY_DEPLOY_PRODUCT_OPS_BASE_URL:-}"
REPORT_DIR="${VERIFY_DEPLOY_REPORT_DIR:-$ROOT/artifacts/stackctl/repeatable/${TARGET}-${MODE}}"

mkdir -p "$REPORT_DIR"

run_once() {
  local index="$1"
  local started ended duration
  started="$(date +%s)"
  if [[ "$MODE" == "cold-build" ]]; then
    python3 agent_ops/deploy/stackctl.py \
      --output-format json \
      --report-dir "$REPORT_DIR/run-${index}" \
      deploy \
      --target "$TARGET" \
      --mode "$MODE" \
      --stage "$STAGE" \
      --image-version "repeatable-${index}" \
      --previous-image-version "repeatable-prev-${index}" \
      ${BASE_URL:+--base-url "$BASE_URL"} \
      ${PRODUCT_OPS_BASE_URL:+--product-ops-base-url "$PRODUCT_OPS_BASE_URL"} \
      >"$REPORT_DIR/run-${index}.json"
  else
    python3 agent_ops/deploy/stackctl.py \
      --output-format json \
      --report-dir "$REPORT_DIR/run-${index}" \
      roll \
      --target "$TARGET" \
      --mode "$MODE" \
      --stage "$STAGE" \
      ${BASE_URL:+--base-url "$BASE_URL"} \
      ${PRODUCT_OPS_BASE_URL:+--product-ops-base-url "$PRODUCT_OPS_BASE_URL"} \
      >"$REPORT_DIR/run-${index}.json"
  fi
  ended="$(date +%s)"
  duration="$((ended - started))"
  python3 - "$REPORT_DIR/run-${index}.json" "$duration" "$MAX_SECONDS" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
duration = int(sys.argv[2])
max_seconds = int(sys.argv[3])
payload = json.loads(path.read_text(encoding="utf-8"))
if int(payload.get("exitCode", 1)) != 0:
    raise SystemExit(f"repeatable deploy failed: {path}")
if duration > max_seconds:
    raise SystemExit(f"repeatable deploy exceeded budget: {duration}s > {max_seconds}s")
print(f"[verify-deploy-repeatable] OK {path.name}: {duration}s <= {max_seconds}s")
PY
}

for i in $(seq 1 "$RUNS"); do
  run_once "$i"
done

python3 - "$REPORT_DIR" "$TARGET" "$MODE" "$STAGE" "$RUNS" "$MAX_SECONDS" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
target = sys.argv[2]
mode = sys.argv[3]
stage = sys.argv[4]
runs = int(sys.argv[5])
max_seconds = int(sys.argv[6])
durations = []
for i in range(1, runs + 1):
    payload = json.loads((report_dir / f"run-{i}.json").read_text(encoding="utf-8"))
    durations.append(payload.get("durationMs", 0) / 1000.0)
summary = {
    "target": target,
    "mode": mode,
    "stage": stage,
    "runs": runs,
    "maxSeconds": max_seconds,
    "durationsSeconds": durations,
    "status": "passed",
}
(report_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
