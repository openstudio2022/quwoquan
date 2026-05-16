#!/usr/bin/env bash
# 验证多云 kustomization 可构建（deploy/kustomization/${CLOUD_PROVIDER}-integration）
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
for cloud in aliyun volcengine huaweicloud; do
  kf="deploy/kustomization/${cloud}-integration"
  if [[ ! -d "$kf" ]]; then
    echo "[verify] FAIL: missing $kf" >&2
    FAIL=1
    continue
  fi
  if $BUILDER "$kf" >/dev/null 2>&1; then
    echo "[verify] OK: $kf builds"
  else
    echo "[verify] FAIL: $kf build failed" >&2
    FAIL=1
  fi
done

if [[ $FAIL -eq 1 ]]; then
  echo "[verify] FAIL: deploy kustomization verification failed" >&2
  exit 1
fi
echo "[verify] OK: deploy kustomization validated"
