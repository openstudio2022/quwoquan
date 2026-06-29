#!/usr/bin/env bash
# Scale-100 verify (17 leaves × ~6 objects) with new Cursor token + composer-2.
set -euo pipefail
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$HOME/qwq_scale_verify}"
export QWQ_RUNTIME_ROOT="${QWQ_RUNTIME_ROOT:-$QWQ_DATA_ROOT/runtime}"
export QWQ_PUBLISH_ROOT="${QWQ_PUBLISH_ROOT:-$QWQ_DATA_ROOT/publish}"
export QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1
export QWQ_MANAGED_AGENT_TIMEOUT_SECONDS=1200
export QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS=1200
export QWQ_CURSOR_WARM_ATTEMPTS=6
export QWQ_CURSOR_BRIDGE_TIMEOUT=60
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${REPO_ROOT}/quwoquan_data/.venv/bin/python"
PLAN='cs100verify_20260626'
SOURCE_TASK='旅行/地域/四川省/景区/四川景点fresh scale100'
FRESH_BATCH='fresh_cs100verify_20260626'
FANOUT_BATCH='fanout_cs100verify_20260626'
FANOUT_TASK='旅行/地域/四川省/四川景区 scale100 宪法重验'

pkill -f cursor-sdk-bridge 2>/dev/null || true
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" env ready

if [[ "${1:-}" == "prepare-only" ]]; then
  "$PY" -u "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e prepare \
    --task "$SOURCE_TASK" --batch "$FRESH_BATCH" --plan "$PLAN" --max-workers 2
  exit 0
fi

if [[ "${1:-}" == "fanout-only" ]]; then
  "$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e fanout-author \
    --plan "$PLAN" --strategy by-partition --concurrency 4
  exit 0
fi

# Ensure fanout partition task is active
"$PY" - <<PY
import yaml
from pathlib import Path
for rel in [
    'tasks/旅行/地域/四川省/景区/四川景点fresh scale100/task.yaml',
    'tasks/旅行/地域/四川省/四川景区 scale100 宪法重验/task.yaml',
]:
    p = Path('${QWQ_DATA_ROOT}') / rel
    if not p.is_file():
        continue
    data = yaml.safe_load(p.read_text())
    if data.get('status') != 'active':
        data['status'] = 'active'
        p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
        print('activated', rel)
PY

# fanout 分区由 author-runner orchestrate 推进 checkpoint，fresh prepare 已完成，勿重复 task run
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e author-runner \
  --plan "$PLAN" --strategy by-partition --runtime local --max-workers 1 \
  --model composer-2.5 --orchestrate

"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e finalize --plan "$PLAN" \
  --runtime local --max-workers 1 --model composer-2.5

"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e verify --plan "$PLAN"

"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" verify scale-readiness \
  --task "$FANOUT_TASK" --batch "$FANOUT_BATCH" --daily-target 100 --target 100 \
  --min-pass-rate 0.9 --mode commercial --allow-missing-import \
  --report-out "${REPO_ROOT}/artifacts/cs100verify_readiness.json"
