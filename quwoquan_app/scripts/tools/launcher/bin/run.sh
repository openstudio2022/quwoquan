#!/usr/bin/env bash
# canonical launcher 的全局 PATH wrapper：任意工作目录可调用 `run.sh`。
# 启动"当前所站的那棵树"：cwd 位于某个 App 树内即 exec 该树的 quwoquan_app/run.sh；
# 不在任何树内时枚举同仓全部 worktree（`--worktree <目录|分支>` 显式、TTY 数字选择、
# 非 TTY typed 阻断），不再静默退回 wrapper 自身所在树。本文件不承载任何启动参数、
# 状态或判定；逻辑唯一归属仓库内 quwoquan_app/run.sh 与 launcher/worktree_selection.py。
set -euo pipefail
anchor_app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
selector="$anchor_app_dir/scripts/tools/launcher/worktree_selection.py"
worktree=""
passthrough=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree)
      [[ -n "${2:-}" ]] || { echo "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive: --worktree requires a directory or branch" >&2; exit 2; }
      worktree="$2"; shift 2 ;;
    --worktree=*) worktree="${1#*=}"; shift ;;
    *) passthrough+=("$1"); shift ;;
  esac
done
launcher="$(PYTHONDONTWRITEBYTECODE=1 python3 "$selector" --anchor-app-dir "$anchor_app_dir" --cwd "$PWD" ${worktree:+--worktree "$worktree"})" || exit $?
exec "$launcher" "${passthrough[@]}"
