#!/usr/bin/env bash
# 删除 quwoquan_data runtime 下的生成产物目录（runs/publish/out/downloads），便于消除旧 schemaVersion 磁盘残留并重跑链路。
# 保留 runtime/specs、runtime/seed、runtime/trees 等人工纳入版本管理的种子与规格。
#
# 用法：
#   QWQ_RUNTIME_ROOT=/path/to/runtime bash scripts/clean_quwoquan_data_runtime_generated.sh
#   FORCE=1 bash scripts/clean_quwoquan_data_runtime_generated.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${QWQ_RUNTIME_ROOT:-$ROOT/quwoquan_data/runtime}"

if [[ "${FORCE:-0}" != "1" ]]; then
  echo "[clean] runtime 根: ${RUNTIME}"
  echo "[clean] 将删除下列目录（若存在）: runs publish out downloads"
  read -r -p "输入 YES 确认: " CONFIRM
  if [[ "${CONFIRM}" != "YES" ]]; then
    echo "取消。" >&2
    exit 3
  fi
fi

for d in runs publish out downloads; do
  tgt="${RUNTIME%/}/$d"
  if [[ -d "$tgt" ]]; then
    echo "[clean] rm -rf $tgt"
    rm -rf "$tgt"
  fi
done

echo "[clean] OK"
exit 0
