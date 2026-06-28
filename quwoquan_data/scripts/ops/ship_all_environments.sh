#!/usr/bin/env bash
# 四环境一键发布：promote → 采样 bundle →（可选）灌库。
# 用法：
#   bash quwoquan_data/scripts/ops/ship_all_environments.sh --task T --batch B
#   bash quwoquan_data/scripts/ops/ship_all_environments.sh --task T --batch B --import --mongo-uri mongodb://127.0.0.1:27017
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
ENVS="${QWQ_SHIP_ENVS:-alpha,beta,gamma,prod}"
EXTRA=()
if [[ "${1:-}" == "--import" ]]; then
  EXTRA+=(--import "$@")
else
  EXTRA=("$@")
fi
python3 quwoquan_data/scripts/cli.py ship \
  --env "$ENVS" \
  --copy-entities \
  "${EXTRA[@]}"
