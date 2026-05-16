#!/usr/bin/env bash
# config_release_rollback.sh — Emergency model bucket rule-only cutover.
# Sets model bucket to 0% (all traffic to rule) for a given environment.
#
# Usage:
#   bash scripts/ml/config_release_rollback.sh --env prod-gray
#   bash scripts/ml/config_release_rollback.sh --env gamma
set -euo pipefail

ENV="${ENV:-prod-gray}"
CONFIG_ROOT="${CONFIG_ROOT:-services/content-service/configs}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --env) ENV="$2"; shift 2 ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
done

CONFIG_FILE="${CONFIG_ROOT}/${ENV}/config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: Config not found: $CONFIG_FILE"
  exit 1
fi

echo "[rule-only-cutover] Setting model bucket to 0% in ${CONFIG_FILE}"

if command -v python3 &>/dev/null; then
  python3 -c "
import yaml, sys

path = '${CONFIG_FILE}'
with open(path) as f:
    cfg = yaml.safe_load(f) or {}

exps = cfg.get('experiments', {})
mvr = exps.get('rec_model_vs_rule', {})
if mvr:
    mvr['buckets'] = {'rule': 100, 'model': 0}
    cfg['experiments']['rec_model_vs_rule'] = mvr

with open(path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    print(f'[rule-only-cutover] Model bucket set to 0% in {path}')
    print(f'[rule-only-cutover] New experiment config: {cfg.get(\"experiments\", {})}')
"
else
  echo "ERROR: python3 not available for YAML manipulation"
  exit 1
fi

echo "[rule-only-cutover] DONE — deploy this config change to take effect"
