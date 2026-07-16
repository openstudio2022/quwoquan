#!/usr/bin/env bash
# 校验 search-service 在单一根 Go module 下的可复现性。
#
# 独立部署由 build target 与 workload mapping 保证，不再用嵌套 go.mod 模拟边界。
# 本门禁验证：
#   1) 根 go.mod/go.sum、Dockerfile 与 cmd 必须 git-tracked。
#   2) search-service 下不得回归嵌套 go.mod/go.sum。
#   3) 根 module 能构建并可选测试 search-service 全包。
#
# 任何一项失败即 GATE_BLOCK：禁止以"功能本地可跑"掩盖未版本落盘导致的 CI 不可复现。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

MODULE_REL="quwoquan_service/services/search-service"
DOCKERFILE_REL="quwoquan_service/services/search-service/deploy/Dockerfile"
WITH_TESTS=0
for arg in "$@"; do
  case "$arg" in
    --with-tests) WITH_TESTS=1 ;;
  esac
done

echo "[verify] search-service root-module reproducibility"

fail() { echo "[verify] FAIL: $1"; exit 1; }

# 1) 关键文件必须存在于工作树
required_files=(
  "quwoquan_service/go.mod"
  "quwoquan_service/go.sum"
  "$MODULE_REL/cmd/api/main.go"
  "$DOCKERFILE_REL"
)
for f in "${required_files[@]}"; do
  [ -f "$f" ] || fail "missing required file: $f"
done

# 2) 根依赖图与关键构建文件必须 git-tracked。
tracked_required=(
  "quwoquan_service/go.mod"
  "quwoquan_service/go.sum"
  "$MODULE_REL/cmd/api/main.go"
  "$DOCKERFILE_REL"
)
untracked=()
for f in "${tracked_required[@]}"; do
  if [ -z "$(git ls-files -- "$f")" ]; then
    untracked+=("$f")
  fi
done
if [ "${#untracked[@]}" -gt 0 ]; then
  echo "[verify] FAIL: 以下 search-service 根 module 关键文件未纳入版本控制："
  for f in "${untracked[@]}"; do echo "  - $f"; done
  exit 1
fi

# 3) 禁止嵌套 module 回归。
[ ! -e "$MODULE_REL/go.mod" ] || fail "nested module is forbidden: $MODULE_REL/go.mod"
[ ! -e "$MODULE_REL/go.sum" ] || fail "nested module lock is forbidden: $MODULE_REL/go.sum"

# 4) 从唯一根 module 构建。
echo "[verify] go build ./services/search-service/..."
( cd quwoquan_service && go build ./services/search-service/... ) || fail "root-module build failed for search-service"

if [ "$WITH_TESTS" -eq 1 ]; then
  echo "[verify] go test ./services/search-service/..."
  ( cd quwoquan_service && go test ./services/search-service/... ) || fail "root-module tests failed for search-service"
fi

echo "[verify] OK: search-service uses one tracked root module"
