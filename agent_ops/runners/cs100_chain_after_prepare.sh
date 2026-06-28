#!/usr/bin/env bash
# Wait for cs100 prepare loop, then fanout + full e2e (composer-2.5).
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
LOG="${QWQ_DATA_ROOT}/cs100_prepare_loop.log"
CHAIN_LOG="${QWQ_DATA_ROOT}/cs100_chain_after_prepare.log"
PLAN='cs100verify_20260626'

exec >>"$CHAIN_LOG" 2>&1
echo "=== cs100_chain_after_prepare start $(date -Iseconds) ==="

while true; do
  if rg -q 'prepare reached produce_compose|prepare exited 0' "$LOG" 2>/dev/null; then
    echo "prepare done detected"
    break
  fi
  if rg -q 'prepare failed exit=' "$LOG" 2>/dev/null; then
    echo "prepare failed; abort chain"
    exit 1
  fi
  sleep 30
done

pkill -f cursor-sdk-bridge 2>/dev/null || true
sleep 1
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" env ready

echo "=== fanout-author $(date -Iseconds) ==="
"$PY" -u "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e fanout-author \
  --plan "$PLAN" --strategy by-partition --concurrency 4

echo "=== resume cs100 e2e $(date -Iseconds) ==="
bash "${REPO_ROOT}/agent_ops/runners/resume_cs100verify_e2e.sh"

echo "=== cs100_chain_after_prepare complete $(date -Iseconds) ==="
