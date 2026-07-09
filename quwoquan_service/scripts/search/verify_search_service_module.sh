#!/usr/bin/env bash
# 校验 search-service 独立 Go module 的可复现性（关闭 R-S06-S-3 的 CI 门禁）。
#
# search-service 是独立 module（module quwoquan_service/services/search-service，
# replace quwoquan_service => ../..），容器构建依赖 go.mod/go.sum 的完整依赖图。
# 此前曾在干净检出/CI 中出现 `missing go.sum entry`，根因是锁文件与源树未纳入
# 版本控制。本门禁在 CI 上以"干净检出视角"验证：
#   1) go.mod / go.sum / Dockerfile / cmd / configs 必须 git-tracked（缺失即不可复现）。
#   2) module 依赖图可解析、可构建（go build ./...）。
#   3) 可选：go test ./...（--with-tests）。
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

echo "[verify] search-service module reproducibility"

fail() { echo "[verify] FAIL: $1"; exit 1; }

# 1) 关键文件必须存在于工作树
required_files=(
  "$MODULE_REL/go.mod"
  "$MODULE_REL/go.sum"
  "$MODULE_REL/cmd/api/main.go"
  "$DOCKERFILE_REL"
)
for f in "${required_files[@]}"; do
  [ -f "$f" ] || fail "missing required file: $f"
done

# 2) 关键文件必须 git-tracked（干净检出/CI 才能复现构建）。
#    这是 R-S06-S-3 的核心：untracked 锁文件会导致 CI 缺失 go.sum 条目而构建失败。
tracked_required=(
  "$MODULE_REL/go.mod"
  "$MODULE_REL/go.sum"
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
  echo "[verify] FAIL: 以下 search-service 关键文件未纳入版本控制（CI 干净检出将不可复现，R-S06-S-3 未闭合）："
  for f in "${untracked[@]}"; do echo "  - $f"; done
  echo "[verify] 修复：git add 上述文件后重跑（含整个 $MODULE_REL/ 源树）。"
  exit 1
fi

# 3) replace 父模块根必须存在（replace quwoquan_service => ../..）
[ -f "quwoquan_service/go.mod" ] || fail "missing parent module quwoquan_service/go.mod (replace target ../..)"

# 4) module 可构建（依赖图可解析）。go mod verify 对 local replace 目标会报
#    missing ziphash（正常），因此用 build 作为可解析性的真证据。
echo "[verify] go build ./... ($MODULE_REL)"
( cd "$MODULE_REL" && go build ./... ) || fail "go build ./... failed in $MODULE_REL"

if [ "$WITH_TESTS" -eq 1 ]; then
  echo "[verify] go test ./... ($MODULE_REL)"
  ( cd "$MODULE_REL" && go test ./... ) || fail "go test ./... failed in $MODULE_REL"
fi

echo "[verify] OK: search-service module tracked + reproducible"
