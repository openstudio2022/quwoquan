#!/usr/bin/env bash
# Resume Scale-10 verify after Cursor SDK recovery (R-CS03).
set -euo pipefail
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$HOME/qwq_scale_verify}"
export QWQ_RUNTIME_ROOT="${QWQ_RUNTIME_ROOT:-$QWQ_DATA_ROOT/runtime}"
export QWQ_PUBLISH_ROOT="${QWQ_PUBLISH_ROOT:-$QWQ_DATA_ROOT/publish}"
export QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1
export QWQ_MANAGED_AGENT_TIMEOUT_SECONDS=900
export QWQ_CURSOR_WARM_ATTEMPTS=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${REPO_ROOT}/quwoquan_data/.venv/bin/python"
TASK='旅行/地域/四川省/四川景区 scale10 宪法重验'
BATCH='fanout_s10verify_20260626'
PLAN='s10verify_20260626'
pkill -f cursor-sdk-bridge 2>/dev/null || true
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" env ready
# reset infra gate if manual_required
"$PY" - <<'PY'
import json
from pathlib import Path
p=Path(f"{__import__('os').environ['QWQ_RUNTIME_ROOT']}/batches/四川景区scale10宪法重验-4ef87320__fanout_s10verify_20260626/_shared/task_workflow_state.json")
if p.exists():
    s=json.loads(p.read_text())
    if s.get('status')=='manual_required':
        s['status']='waiting_agent'
        s['infrastructureRetryCounts']={}
        p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
    (p.parent/'controller_lease.json').unlink(missing_ok=True)
PY
"$PY" -u "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task run --mode single \
  --task "$TASK" --batch "$BATCH" --managed --runtime local --resume --max-workers 1 --model composer-2
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e author-runner \
  --plan "$PLAN" --strategy by-partition --runtime local --max-workers 2 --orchestrate
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e finalize --plan "$PLAN"
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" task scaled-e2e verify --plan "$PLAN"
"$PY" "${REPO_ROOT}/quwoquan_data/scripts/cli.py" verify scale-readiness \
  --task "$TASK" --batch "$BATCH" --daily-target 10 --target 10 --min-pass-rate 1.0 \
  --mode trial --report-out "${REPO_ROOT}/artifacts/s10verify_readiness.json"
