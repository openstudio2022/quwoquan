#!/usr/bin/env bash
# End-to-end supervisor: cs100 prepare → e2e → cs1000 (logs under artifacts + QWQ_DATA_ROOT).
set -euo pipefail
export CURSOR_API_KEY="${CURSOR_API_KEY:?set CURSOR_API_KEY}"
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.qwq_sandbox}"
export QWQ_RUNTIME_ROOT="${QWQ_RUNTIME_ROOT:-$QWQ_DATA_ROOT/runtime}"
export QWQ_PUBLISH_ROOT="${QWQ_PUBLISH_ROOT:-$QWQ_DATA_ROOT/publish}"
export QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1
export QWQ_MANAGED_AGENT_TIMEOUT_SECONDS=1200
export QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS=1200
export QWQ_CURSOR_WARM_ATTEMPTS=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${REPO_ROOT}/quwoquan_data/.venv/bin/python"
ART="${REPO_ROOT}/artifacts/quwoquan_data_runs"
PREP_LOG="${QWQ_DATA_ROOT}/cs100_prepare_loop.log"
SUP_LOG="${ART}/scale_verify_supervisor.log"
mkdir -p "$ART"
exec >>"$SUP_LOG" 2>&1

log() { echo "[$(date -Iseconds)] $*"; }

wait_prepare() {
  log "waiting cs100 prepare (produce_compose)..."
  while true; do
    if rg -q 'prepare reached produce_compose|prepare exited 0|已到 produce_compose' "$PREP_LOG" 2>/dev/null; then
      log "cs100 prepare DONE"
      return 0
    fi
    if rg -q 'prepare failed exit=' "$PREP_LOG" 2>/dev/null; then
      log "cs100 prepare FAILED"
      tail -30 "$PREP_LOG"
      return 1
    fi
    ent="$(rg 'Entity done' "$PREP_LOG" 2>/dev/null | tail -1 || true)"
    log "prepare progress: ${ent:-unknown}"
    sleep 120
  done
}

run_cs100_e2e() {
  log "=== cs100 e2e start ==="
  pkill -f cursor-sdk-bridge 2>/dev/null || true
  sleep 2
  "$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" env ready | tee "${ART}/cs100_env_ready.log"
  bash "${REPO_ROOT}/agent_ops/runners/cs100_chain_after_prepare.sh" 2>&1 | tee "${ART}/cs100_e2e_run.log"
  rc=${PIPESTATUS[0]}
  log "cs100 e2e exit=$rc"
  return "$rc"
}

run_cs1000() {
  log "=== cs1000 pipeline start ==="
  bash "${REPO_ROOT}/agent_ops/runners/cs1000_prepare_loop.sh" 60 2>&1 | tee "${ART}/cs1000_prepare_run.log"
  pkill -f cursor-sdk-bridge 2>/dev/null || true
  bash "${REPO_ROOT}/agent_ops/runners/resume_cs1000verify_e2e.sh" 2>&1 | tee "${ART}/cs1000_e2e_run.log"
  rc=${PIPESTATUS[0]}
  log "cs1000 e2e exit=$rc"
  return "$rc"
}

log "supervisor start plan=10→100→1000"
if wait_prepare; then
  # cs100_chain may already be running; run e2e wrapper once.
  if rg -q 'cs100_chain_after_prepare complete' "${QWQ_DATA_ROOT}/cs100_chain_after_prepare.log" 2>/dev/null; then
    log "cs100 chain already complete"
  else
    run_cs100_e2e || log "cs100 e2e failed — see ${ART}/cs100_e2e_run.log"
  fi
  if rg -q '"decision": "go"' "${REPO_ROOT}/artifacts/cs100verify_readiness.json" 2>/dev/null; then
    log "cs100 scale-readiness GO"
    run_cs1000 || log "cs1000 failed — see ${ART}/cs1000_e2e_run.log"
  else
    log "cs100 not GO yet; skip cs1000"
  fi
else
  log "abort: prepare failed"
  exit 1
fi
log "supervisor end"
