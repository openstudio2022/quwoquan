#!/usr/bin/env bash
# Entry for Cursor Shell background: runs gate supervisor in foreground (no nohup).
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
GATE_LOG="${QWQ_DATA_ROOT}/cs100_fresh_to_gate.log"
mkdir -p "$QWQ_DATA_ROOT"
echo "[$(date -Iseconds)] start_cs100_supervisors: launching gate (foreground)" | tee -a "$GATE_LOG"
exec bash "${REPO_ROOT}/agent_ops/runners/cs100_fresh_to_gate.sh" 2>&1 | tee -a "$GATE_LOG"
