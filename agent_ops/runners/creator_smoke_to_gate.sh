#!/usr/bin/env bash
# 底稿中心创作冒烟 supervisor：驱动 single-mode 全 DAG → post-package verify → trial scale-readiness。
# 仅从用户 Terminal 或后台 setsid 启动。
set -euo pipefail
export CURSOR_API_KEY="${CURSOR_API_KEY:?set CURSOR_API_KEY}"
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.qwq_sandbox}"
export QWQ_RUNTIME_ROOT="${QWQ_RUNTIME_ROOT:-$QWQ_DATA_ROOT/runtime}"
export QWQ_PUBLISH_ROOT="${QWQ_PUBLISH_ROOT:-$QWQ_DATA_ROOT/publish}"
export QWQ_RELEASE_ROOT="${QWQ_RELEASE_ROOT:-$QWQ_DATA_ROOT/release}"
export QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1
export QWQ_MANAGED_AGENT_TIMEOUT_SECONDS=1200
export QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS=1200
export QWQ_CURSOR_WARM_ATTEMPTS=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${REPO_ROOT}/quwoquan_data/.venv/bin/python"
TASK="${SMOKE_TASK:-旅行/地域/四川省/景区/创作冒烟试跑}"
BATCH="${SMOKE_BATCH:-creator_smoke_20260629}"
LOG="${QWQ_DATA_ROOT}/creator_smoke_run.log"
ART="${REPO_ROOT}/artifacts"
mkdir -p "$ART"

loop_alive() {
  pgrep -f "cli.py task run.*${BATCH}" >/dev/null \
    || pgrep -f "creator_smoke_resume_loop" >/dev/null
}

run_readiness() {
  echo "[$(date -Iseconds)] post-package verify"
  "$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" verify --task "$TASK" --batch "$BATCH" \
    2>&1 | tee "${ART}/creator_smoke_verify.log" || true
  echo "[$(date -Iseconds)] trial scale-readiness"
  "$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" verify scale-readiness \
    --task "$TASK" --batch "$BATCH" --daily-target 3 --target 3 --min-pass-rate 1.0 \
    --mode trial --allow-missing-import \
    --report-out "${ART}/creator_smoke_readiness.json" \
    2>&1 | tee "${ART}/creator_smoke_scale_readiness.log"
}

if [[ "${1:-}" == "readiness-only" ]]; then
  run_readiness
  exit 0
fi

if ! loop_alive; then
  bash "${REPO_ROOT}/agent_ops/runners/creator_smoke_resume_loop.sh" 200 >>"$LOG" 2>&1 &
  sleep 3
fi

while true; do
  if rg -q 'WORKFLOW COMPLETE|workflow complete' "$LOG" 2>/dev/null; then
    echo "[$(date -Iseconds)] smoke workflow complete"
    break
  fi
  if rg -q 'creator smoke failed exit=' "$LOG" 2>/dev/null && ! loop_alive; then
    echo "[$(date -Iseconds)] smoke pipeline stopped with error"; tail -40 "$LOG"; exit 1
  fi
  if ! loop_alive; then
    echo "[$(date -Iseconds)] resume loop not alive; restarting"
    bash "${REPO_ROOT}/agent_ops/runners/creator_smoke_resume_loop.sh" 200 >>"$LOG" 2>&1 &
    sleep 3
  fi
  st=$(python3 - <<PY 2>/dev/null || true
import json, glob, os
root=os.environ["QWQ_RUNTIME_ROOT"]
cands=glob.glob(os.path.join(root,"batches","*${BATCH}","_shared","task_workflow_state.json"))
if cands:
    s=json.loads(open(cands[0]).read())
    la=s.get("lastAgentRun") or {}
    print(s.get("status",""), s.get("waitingCheckpoint",""), "fin=",la.get("finishedCount","?"), "done=",len(s.get("completed") or []))
else:
    print("no workflow state yet")
PY
)
  echo "[$(date -Iseconds)] smoke: $st"
  sleep 120
done

run_readiness
echo "[$(date -Iseconds)] creator_smoke_to_gate complete"
