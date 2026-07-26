#!/usr/bin/env bash
# 验证四个环境装配入口均可独立构建。
# kustomize 或 kubectl 未安装时跳过
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

if ! command -v kustomize &>/dev/null && ! command -v kubectl &>/dev/null; then
  echo "[verify] SKIP: kustomize/kubectl not found — deploy kustomization check skipped"
  exit 0
fi

BUILDER=""
if command -v kustomize &>/dev/null; then
  BUILDER="kustomize build"
elif command -v kubectl &>/dev/null; then
  BUILDER="kubectl kustomize"
fi

FAIL=0
for env_name in alpha beta gamma prod; do
  environment_root="quwoquan_ops/environments/${env_name}"
  if [[ ! -d "$environment_root" ]]; then
    echo "[verify] FAIL: missing $environment_root" >&2
    FAIL=1
    continue
  fi
  if $BUILDER "$environment_root" >/dev/null 2>&1; then
    echo "[verify] OK: $environment_root builds"
  else
    echo "[verify] FAIL: $environment_root build failed" >&2
    FAIL=1
  fi
done

if [[ $FAIL -eq 1 ]]; then
  echo "[verify] FAIL: deploy kustomization verification failed" >&2
  exit 1
fi
echo "[verify] OK: deploy kustomization validated"
