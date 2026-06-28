#!/usr/bin/env bash
# Scale 放量执行期监控：SDK / workflow / fanout / object_queue 快照
set -euo pipefail

PLAN="${1:-}"
DATA_ROOT="${QWQ_DATA_ROOT:-$HOME/qwq_scale_verify}"
RUNTIME="$DATA_ROOT/runtime"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

echo "=== scale_verify_monitor @ $STAMP plan=$PLAN ==="

if command -v python3 >/dev/null 2>&1; then
  python3 /Users/zhaoyuxi/Projects/quwoquan/quwoquan_data/scripts/cli.py env preflight --cursor-startup 2>/dev/null | tail -5 || true
fi

bridge_count="$(pgrep -fl cursor-sdk-bridge 2>/dev/null | wc -l | tr -d ' ')"
echo "cursor-sdk-bridge processes: $bridge_count"

if [[ -n "$PLAN" && -f "$RUNTIME/_shared/orchestrate/$PLAN/run_matrix.json" ]]; then
  echo "--- run_matrix summary ---"
  python3 - <<PY
import json
from pathlib import Path
p = Path("$RUNTIME/_shared/orchestrate/$PLAN/run_matrix.json")
m = json.loads(p.read_text())
orch = m.get("orchestrators") or []
reached = sum(1 for o in orch if o.get("reached"))
print(f"orchestrators={len(orch)} reached={reached}")
for o in orch[-5:]:
    print(o.get("taskId"), o.get("batchId"), o.get("worker"), "reached=", o.get("reached"), "error=", (o.get("error") or "")[:80])
PY
fi

echo "--- recent workflow states ---"
find "$RUNTIME/batches" -name task_workflow_state.json 2>/dev/null | head -20 | while read -r f; do
  python3 - <<PY
import json
from pathlib import Path
s = json.loads(Path("$f").read_text())
print(Path("$f").parent.name, "status=", s.get("status"), "wait=", s.get("waitingCheckpoint"), "next=", (s.get("nextAction") or "")[:60])
hist = s.get("agentRunHistory") or []
if hist:
    last = hist[-1]
    print("  lastAgent stage=", last.get("stage"), "infra=", last.get("infrastructureFailures"), "finished=", last.get("finishedCount"))
PY
done

echo "--- object_queue dead/startup_failed (sample) ---"
find "$RUNTIME/batches" -path '*/_shared/object_queue/*.json' 2>/dev/null | while read -r j; do
  state="$(python3 -c "import json;print(json.load(open('$j')).get('state',''))" 2>/dev/null || echo '')"
  if [[ "$state" == "dead" || "$state" == "startup_failed" ]]; then
    echo "$j state=$state"
  fi
done | head -15

echo "=== end monitor ==="
