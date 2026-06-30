#!/usr/bin/env bash
# Wait for cs100 e2e chain, then start cs1000 prepare (avoid bridge contention).
set -euo pipefail
export CURSOR_API_KEY="${CURSOR_API_KEY:?set CURSOR_API_KEY}"
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.qwq_sandbox}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CS100_LOG="${QWQ_DATA_ROOT}/cs100_chain_after_prepare.log"
CS1000_LOG="${QWQ_DATA_ROOT}/cs1000_prepare_loop.log"
exec >>"${QWQ_DATA_ROOT}/cs1000_chain_watcher.log" 2>&1
echo "=== cs1000_chain_after_cs100 start $(date -Iseconds) ==="
while true; do
  if rg -q 'cs100_chain_after_prepare complete' "$CS100_LOG" 2>/dev/null; then
    echo "cs100 complete; starting cs1000 prepare"
    break
  fi
  if rg -q 'prepare failed; abort chain|cs100.*FAILED' "$CS100_LOG" 2>/dev/null; then
    echo "cs100 chain failed; still starting cs1000 prepare after delay"
    sleep 300
    break
  fi
  sleep 120
done
bash "${REPO_ROOT}/agent_ops/runners/cs1000_prepare_loop.sh" 60
