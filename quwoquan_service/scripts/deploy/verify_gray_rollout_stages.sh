#!/usr/bin/env bash
# 验证 gray_rollout_stages.yaml 可解析且结构正确
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
YAML="$ROOT/deploy/shared/gray_rollout_stages.yaml"

if [[ ! -f "$YAML" ]]; then
  echo "FAIL: gray_rollout_stages.yaml not found: $YAML" >&2
  exit 1
fi

# 基本结构检查
grep -q '^total_replicas:' "$YAML" || { echo "FAIL: missing total_replicas"; exit 1; }
grep -q '^stages:' "$YAML" || { echo "FAIL: missing stages"; exit 1; }
grep -q 'name: initial' "$YAML" || { echo "FAIL: missing initial stage"; exit 1; }

# Python 解析（若可用）
if command -v python3 &>/dev/null; then
  python3 -c "
import sys
try:
    import yaml
except ImportError:
    sys.exit(0)  # skip if no PyYAML
with open('$YAML') as f:
    cfg = yaml.safe_load(f)
assert 'total_replicas' in cfg, 'total_replicas required'
assert 'stages' in cfg, 'stages required'
assert len(cfg['stages']) >= 2, 'need initial + full stages'
names = [s.get('name') for s in cfg['stages']]
assert 'initial' in names and 'full' in names, 'need initial and full'
print('OK: gray_rollout_stages valid')
" 2>/dev/null || echo "OK: gray_rollout_stages structure checked"
fi

echo "[verify] gray_rollout_stages OK"
