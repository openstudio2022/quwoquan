#!/usr/bin/env bash
# Scale-1000 verify (170 leaves × ~6 objects) after prepare completes.
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
PLAN='cs1000verify_20260626'
TASK='旅行/地域/四川省/景区/四川景点 scale1000'
FANOUT_BATCH='fanout_cs1000verify_20260626'

pkill -f cursor-sdk-bridge 2>/dev/null || true
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" env ready

"$PY" -u "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e fanout-author \
  --plan "$PLAN" --strategy by-partition --concurrency 4

"$PY" -u "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task run --mode single \
  --task "$TASK" --batch "$FANOUT_BATCH" --managed --runtime local \
  --resume --max-workers 1 --model composer-2.5 --force-clean-workspace-agent-state

"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e author-runner \
  --plan "$PLAN" --strategy by-partition --runtime local --max-workers 2 \
  --model composer-2.5 --orchestrate

"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e finalize --plan "$PLAN" \
  --runtime local --max-workers 1 --model composer-2.5

"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e verify --plan "$PLAN"

"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" verify scale-readiness \
  --task "$TASK" --batch "$FANOUT_BATCH" --daily-target 1000 --target 1000 \
  --min-pass-rate 0.9 --mode commercial --allow-missing-import \
  --report-out "${REPO_ROOT}/artifacts/cs1000verify_readiness.json"
