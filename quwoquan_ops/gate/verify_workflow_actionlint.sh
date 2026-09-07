#!/usr/bin/env bash
# workflow 文件级左移门：actionlint（pinned 版本，二进制缓存于 .qwq_output）。
# 拦截 GitHub Actions 解析期即失效的错误：非法上下文（job.workflow_ref、job 级 env 引用 runner.*）、
# 不存在的属性（github.run_started_at）、reusable workflow 输入类型不匹配等。
# workflow↔仓内 CLI 的 argparse required 一致性由 verify_workflow_cli_arguments.py 单独负责。
# 只在 .github/workflows/** 变更时由 commit-gate 选中；工具不可用且无法离线安装则 fail closed。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
ACTIONLINT_VERSION="${ACTIONLINT_VERSION:-1.7.7}"
CACHE_ROOT="$QWQ_OUTPUT_ROOT/env/repo/local/cache/actionlint/$ACTIONLINT_VERSION"
BIN="$CACHE_ROOT/actionlint"

if [[ ! -x "$BIN" ]]; then
  if command -v actionlint >/dev/null 2>&1 && [[ "$(actionlint -version | head -n1)" == "$ACTIONLINT_VERSION" ]]; then
    mkdir -p "$CACHE_ROOT" && ln -sf "$(command -v actionlint)" "$BIN"
  elif command -v go >/dev/null 2>&1; then
    mkdir -p "$CACHE_ROOT"
    GOFLAGS=-mod=mod GOBIN="$CACHE_ROOT" GOMODCACHE="${GOMODCACHE:-$HOME/.cache/quwoquan/go-mod}" \
      go install "github.com/rhysd/actionlint/cmd/actionlint@v${ACTIONLINT_VERSION}" >"$CACHE_ROOT/install.log" 2>&1 || {
      echo "[workflow-actionlint] GATE_BLOCK: actionlint v${ACTIONLINT_VERSION} 不可用且 go install 失败，见 $CACHE_ROOT/install.log" >&2
      exit 2
    }
  else
    echo "[workflow-actionlint] GATE_BLOCK: 缺 actionlint v${ACTIONLINT_VERSION} 且无 go 工具链" >&2
    exit 2
  fi
fi

# -shellcheck= / -pyflakes= 显式禁用外部 linter，避免依赖本机安装；只做 workflow 语法/表达式/上下文校验。
# 仓库级配置（self-hosted runner label 等）来自 .github/actionlint.yaml，由 actionlint 自动发现。
"$BIN" -shellcheck= -pyflakes= .github/workflows/*.yml
echo "[workflow-actionlint] OK"
