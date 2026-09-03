#!/usr/bin/env bash
set -euo pipefail

# 仓库根先由脚本位置推导，再由 git 复核一次。这里历史上写成 `/../../..`，多退了一级
# 落到仓库外的父目录，`git config` 在非仓库目录静默失败，结果 core.hooksPath 长期未
# 设置，pre-commit 与 pre-push 从未生效过。层级计数不自证，必须复核。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$TOPLEVEL" || "$TOPLEVEL" != "$ROOT" ]]; then
  echo "[hooks] refusing to install: '$ROOT' is not the git toplevel (got '${TOPLEVEL:-none}')" 1>&2
  exit 2
fi

hook_dir="$ROOT/quwoquan_ops/hooks"
required_hooks=(pre-commit pre-push post-commit)

for hook in "${required_hooks[@]}"; do
  if [[ ! -f "$hook_dir/$hook" ]]; then
    echo "[hooks] missing required hook: $hook_dir/$hook" 1>&2
    exit 2
  fi
done

git config core.hooksPath quwoquan_ops/hooks
for hook in "${required_hooks[@]}"; do
  chmod +x "$hook_dir/$hook"
done

# 回读证明安装成立。只看 `git config` 的退出码不够——它在错误目录下也可能成功。
installed="$(git config --get core.hooksPath || true)"
if [[ "$installed" != "quwoquan_ops/hooks" ]]; then
  echo "[hooks] install failed: core.hooksPath readback='${installed:-unset}'" 1>&2
  exit 2
fi

echo "[hooks] installed via core.hooksPath=quwoquan_ops/hooks (readback ok)"
echo "[hooks] pre-commit: staged boundary（secret/PII、generated 边界、branch policy）; pre-push: branch policy; post-commit: 未合入工作副本提醒"
