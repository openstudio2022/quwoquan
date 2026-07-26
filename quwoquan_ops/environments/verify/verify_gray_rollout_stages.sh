#!/usr/bin/env bash
# 验证 gray_rollout_stages.yaml 可解析且结构正确
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
YAML="$ROOT/quwoquan_ops/environments/prod/rollout/stages.yaml"

if [[ ! -f "$YAML" ]]; then
  echo "FAIL: gray_rollout_stages.yaml not found: $YAML" >&2
  exit 1
fi

# 基本结构检查
grep -q '^stages:' "$YAML" || { echo "FAIL: missing stages"; exit 1; }
grep -q 'name: gray-initial' "$YAML" || { echo "FAIL: missing gray-initial stage"; exit 1; }

# Python 解析
python3 -c "
import yaml
with open('$YAML') as f:
    cfg = yaml.safe_load(f)
assert 'stages' in cfg, 'stages required'
expected = {'gray-initial': (5, 'gray'), 'carry-on': (25, 'gray'), 'full': (100, 'prod')}
actual = {
    stage.get('name'): (stage.get('step'), stage.get('execution_target'))
    for stage in cfg['stages']
}
assert actual == expected, f'canonical stage drift: {actual}'
forbidden = {
    'replicas', 'min_dwell_seconds', 'min_samples', 'approval_required',
    'auto', 'traffic_target'
}
for stage in cfg['stages']:
    overlap = forbidden & set(stage)
    assert not overlap, f'stage {stage.get(\"name\")} carries forbidden fields: {sorted(overlap)}'
    assert stage.get('routing_profile') == stage.get('name')
    assert stage.get('rollback_on_slo_gate') is True
print('OK: gray_rollout_stages valid')
"

echo "[verify] gray_rollout_stages OK"
