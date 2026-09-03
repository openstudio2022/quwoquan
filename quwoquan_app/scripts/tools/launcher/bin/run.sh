#!/usr/bin/env bash
# canonical launcher 的全局 PATH wrapper：任意工作目录可调用 `run.sh`。
# 启动"当前所站的那棵树"：从 cwd 向上找本 App 根（pubspec 旁有 run.sh 且同仓有
# quwoquan_ops/cli/stackctl.py，或仓库根下的 quwoquan_app/）；找不到时退回
# wrapper 自身所在树。本文件不承载任何参数、状态或判定；逻辑唯一归属仓库内
# quwoquan_app/run.sh。
set -euo pipefail
launcher="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/run.sh"
dir="$PWD"
while :; do
  if [[ -f "$dir/pubspec.yaml" && -f "$dir/run.sh" && ! -L "$dir/run.sh" \
     && -f "$dir/../quwoquan_ops/cli/stackctl.py" ]]; then
    launcher="$dir/run.sh"
    break
  fi
  if [[ -f "$dir/quwoquan_app/pubspec.yaml" && -f "$dir/quwoquan_app/run.sh" \
     && -f "$dir/quwoquan_ops/cli/stackctl.py" ]]; then
    launcher="$dir/quwoquan_app/run.sh"
    break
  fi
  [[ "$dir" != "/" ]] || break
  dir="$(dirname "$dir")"
done
exec "$launcher" "$@"
