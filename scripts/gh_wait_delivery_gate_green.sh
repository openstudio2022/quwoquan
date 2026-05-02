#!/usr/bin/env bash
# 在 git push 到远端分支后，等待「03. Delivery Gate」对应 workflow 成功完成。
# 依赖：已安装 gh 且已 gh auth login；或设置 GITHUB_TOKEN + GITHUB_REPOSITORY。
#
# 用法：
#   bash scripts/gh_wait_delivery_gate_green.sh dev1.0
#   bash scripts/gh_wait_delivery_gate_green.sh dev1.0 3600   # 最多等 3600 秒
set -euo pipefail

BRANCH="${1:-dev1.0}"
MAX_WAIT_SEC="${2:-3600}"

if ! command -v gh >/dev/null 2>&1; then
  echo "FAIL: 需要安装 GitHub CLI (gh): https://cli.github.com/" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)}"
if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
  echo "FAIL: 无法解析 GITHUB_REPOSITORY，请在仓库根目录执行或手动 export。" >&2
  exit 2
fi

TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [[ -z "$TOKEN" ]] && command -v gh >/dev/null 2>&1; then
  TOKEN="$(gh auth token 2>/dev/null || true)"
fi
if [[ -z "$TOKEN" ]]; then
  echo "FAIL: 请设置 GITHUB_TOKEN / GH_TOKEN，或执行 gh auth login。" >&2
  exit 2
fi
export GITHUB_TOKEN="$TOKEN"

exec python3 scripts/ci_assert_delivery_gate_green_for_branch.py "$BRANCH" \
  --wait-seconds "$MAX_WAIT_SEC" \
  --poll-interval 25
