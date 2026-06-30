#!/usr/bin/env bash
# Resume cs100 prepare waves until produce_compose or failure.
set -euo pipefail
export CURSOR_API_KEY="${CURSOR_API_KEY:?set CURSOR_API_KEY}"
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.qwq_sandbox}"
export QWQ_RUNTIME_ROOT="${QWQ_RUNTIME_ROOT:-$QWQ_DATA_ROOT/runtime}"
export QWQ_PUBLISH_ROOT="${QWQ_PUBLISH_ROOT:-$QWQ_DATA_ROOT/publish}"
export QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1
export QWQ_MANAGED_AGENT_TIMEOUT_SECONDS=1200
export QWQ_CURSOR_WARM_ATTEMPTS=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${REPO_ROOT}/quwoquan_data/.venv/bin/python"
LOG="${QWQ_DATA_ROOT}/cs100_prepare_loop.log"
TASK='旅行/地域/四川省/景区/四川景点fresh scale100'
BATCH="${CS100_BATCH:-fresh_cs100verify_20260629}"
MAX_ROUNDS="${1:-30}"
round=0
while (( round < MAX_ROUNDS )); do
  round=$((round + 1))
  echo "=== prepare resume round ${round}/${MAX_ROUNDS} $(date -Iseconds) ===" | tee -a "$LOG"
  pkill -f cursor-sdk-bridge 2>/dev/null || true
  set +e
  "$PY" -u "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task run --mode single \
    --task "$TASK" --batch "$BATCH" --managed --runtime local \
    --agent-provider cursor_sdk --model composer-2.5 --max-workers 1 --resume \
    --until produce_compose --force-clean-workspace-agent-state 2>&1 | tee -a "$LOG"
  code=$?
  set -e
  if rg -q '已到 produce_compose|produce_compose.*completed|stopped_at_until.*produce_compose' "$LOG" 2>/dev/null; then
    echo "prepare reached produce_compose" | tee -a "$LOG"
    exit 0
  fi
  if [[ "$code" -eq 0 ]]; then
    echo "prepare exited 0" | tee -a "$LOG"
    exit 0
  fi
  if [[ "$code" -ne 10 ]]; then
    echo "prepare failed exit=$code" | tee -a "$LOG"
    exit "$code"
  fi
  sleep 2
done
echo "prepare max rounds exceeded" | tee -a "$LOG"
exit 1
