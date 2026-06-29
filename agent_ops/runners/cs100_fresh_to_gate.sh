#!/usr/bin/env bash
# cs100: fresh batch author→publish → commercial scale-readiness (uses prepared fresh batch).
set -euo pipefail
export CURSOR_API_KEY="${CURSOR_API_KEY:?set CURSOR_API_KEY}"
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$HOME/qwq_scale_verify}"
export QWQ_RUNTIME_ROOT="${QWQ_RUNTIME_ROOT:-$QWQ_DATA_ROOT/runtime}"
export QWQ_PUBLISH_ROOT="${QWQ_PUBLISH_ROOT:-$QWQ_DATA_ROOT/publish}"
export QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1
export QWQ_MANAGED_AGENT_TIMEOUT_SECONDS=1200
export QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS=1200
export QWQ_CURSOR_WARM_ATTEMPTS=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${REPO_ROOT}/quwoquan_data/.venv/bin/python"
TASK='旅行/地域/四川省/景区/四川景点fresh scale100'
BATCH="${CS100_BATCH:-fresh_cs100verify_20260629}"
PLAN='cs100verify_20260626'
LOG="${QWQ_DATA_ROOT}/cs100_fresh_author_run.log"
ART="${REPO_ROOT}/artifacts/quwoquan_data_runs"
mkdir -p "$ART"

task_run_alive() {
  pgrep -f "cli.py task run.*${BATCH}" >/dev/null \
    || pgrep -f "cs100_author_resume_loop" >/dev/null
}

ensure_author_resume_loop() {
  if task_run_alive; then
    return 0
  fi
  if rg -q 'WORKFLOW COMPLETE|workflow complete' "$LOG" 2>/dev/null; then
    return 0
  fi
  echo "[$(date -Iseconds)] restarting cs100_author_resume_loop (no live task run)"
  if pgrep -f "cs100_author_resume_loop.sh" >/dev/null; then
    return 0
  fi
  bash "${REPO_ROOT}/agent_ops/runners/cs100_author_resume_loop.sh" 200 >>"$LOG" 2>&1 &
  sleep 5
}

wait_author_publish() {
  while true; do
    if rg -q 'WORKFLOW COMPLETE|workflow complete' "$LOG" 2>/dev/null; then
      return 0
    fi
    st=$(python3 - <<PY
import json
from pathlib import Path
p=Path("${QWQ_DATA_ROOT}/runtime/batches/四川景点freshscale10-26aad552__${BATCH}/_shared/task_workflow_state.json")
s=json.loads(p.read_text())
la=s.get('lastAgentRun') or {}
print(s.get('status',''), s.get('waitingCheckpoint',''), la.get('finishedCount','?'), len(s.get('completed') or []))
PY
)
    echo "[$(date -Iseconds)] cs100 fresh pipeline: $st"
    if rg -q 'manual_required|GATE_BLOCK' "$LOG" 2>/dev/null; then
      if ! task_run_alive; then
        echo "pipeline stopped with error"; tail -40 "$LOG"; return 1
      fi
    fi
    if ! task_run_alive; then
      if rg -q 'WORKFLOW COMPLETE' "$LOG" 2>/dev/null; then return 0; fi
      ensure_author_resume_loop
    fi
    sleep 180
  done
}

run_readiness() {
  cp "$LOG" "${ART}/cs100_fresh_author_run.log" 2>/dev/null || true
  "$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" verify scale-readiness \
    --task "$TASK" --batch "$BATCH" --daily-target 100 --target 100 \
    --min-pass-rate 0.9 --mode commercial --allow-missing-import \
    --report-out "${REPO_ROOT}/artifacts/cs100verify_readiness.json" \
    2>&1 | tee "${ART}/cs100_scale_readiness.log"
}

if [[ "${1:-}" == "readiness-only" ]]; then
  run_readiness
  exit 0
fi

if ! task_run_alive; then
  if ! pgrep -f "cs100_author_resume_loop.sh" >/dev/null; then
    bash "${REPO_ROOT}/agent_ops/runners/cs100_author_resume_loop.sh" 200 >>"$LOG" 2>&1 &
  fi
  sleep 3
fi

wait_author_publish
run_readiness
decision=$(python3 -c "import json; print(json.load(open('${REPO_ROOT}/artifacts/cs100verify_readiness.json')).get('decision',''))")
echo "cs100 decision=$decision"
if [[ "$decision" != "go" ]]; then exit 1; fi

# cs1000 after cs100 go
bash "${REPO_ROOT}/agent_ops/runners/cs1000_prepare_loop.sh" 60 2>&1 | tee "${ART}/cs1000_prepare_run.log"
bash "${REPO_ROOT}/agent_ops/runners/resume_cs1000verify_e2e.sh" 2>&1 | tee "${ART}/cs1000_e2e_run.log"
