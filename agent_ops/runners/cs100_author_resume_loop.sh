#!/usr/bin/env bash
# Resume cs100 fresh batch from produce_author → publish (managed local, composer-2.5).
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
LOG="${QWQ_DATA_ROOT}/cs100_fresh_author_run.log"
LOCK="${QWQ_DATA_ROOT}/cs100_author_resume.pid"
TASK='旅行/地域/四川省/景区/四川景点fresh scale100'
BATCH="${CS100_BATCH:-fresh_cs100verify_20260629}"
MAX_ROUNDS="${1:-200}"
if [[ -f "$LOCK" ]]; then
  oldpid="$(cat "$LOCK" 2>/dev/null || true)"
  if [[ -n "$oldpid" ]] && kill -0 "$oldpid" 2>/dev/null; then
    echo "cs100_author_resume_loop: already running pid=$oldpid $(date -Iseconds)" | tee -a "$LOG"
    exit 0
  fi
fi
echo "$$" >"$LOCK"
trap 'rm -f "$LOCK"' EXIT
round=0
while (( round < MAX_ROUNDS )); do
  round=$((round + 1))
  echo "=== cs100 author resume round ${round}/${MAX_ROUNDS} $(date -Iseconds) ===" | tee -a "$LOG"
  if rg -q 'WORKFLOW COMPLETE' "$LOG" 2>/dev/null; then
    echo "cs100 workflow complete" | tee -a "$LOG"
    exit 0
  fi
  if pgrep -f "cli.py task run.*${BATCH}" >/dev/null; then
    echo "task run already active; waiting" | tee -a "$LOG"
    sleep 60
    continue
  fi
  set +e
  "$PY" -u "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task run --mode single \
    --task "$TASK" --batch "$BATCH" --managed --runtime local \
    --agent-provider cursor_sdk --model composer-2.5 --max-workers 1 --resume \
    --force-clean-workspace-agent-state 2>&1 | tee -a "$LOG"
  code=$?
  set -e
  if rg -q 'WORKFLOW COMPLETE' "$LOG" 2>/dev/null; then
    echo "cs100 workflow complete" | tee -a "$LOG"
    exit 0
  fi
  if [[ "$code" -eq 0 ]]; then
    echo "task run exited 0 without WORKFLOW COMPLETE" | tee -a "$LOG"
    exit 0
  fi
  if [[ "$code" -ne 10 ]]; then
    echo "cs100 author failed exit=$code" | tee -a "$LOG"
    exit "$code"
  fi
  sleep 2
done
echo "cs100 author max rounds exceeded" | tee -a "$LOG"
exit 1
