#!/usr/bin/env bash
# 部署到 integration 环境，支持 CLOUD_PROVIDER 切换（aliyun|volcengine|huaweicloud）
# 入口文件：deploy/kustomization/${CLOUD_PROVIDER}.integration.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLOUD_PROVIDER="${CLOUD_PROVIDER:-aliyun}"
KUSTOMIZATION="deploy/kustomization/${CLOUD_PROVIDER}.integration.yaml"

if [[ ! -f "$KUSTOMIZATION" ]]; then
  echo "FAIL: kustomization not found: $KUSTOMIZATION" >&2
  echo "CLOUD_PROVIDER must be one of: aliyun, volcengine, huaweicloud" >&2
  exit 1
fi

echo "[deploy] integration (CLOUD_PROVIDER=$CLOUD_PROVIDER)"
echo "[deploy] building: $KUSTOMIZATION"

if command -v kustomize &>/dev/null; then
  kustomize build -f "$KUSTOMIZATION"
elif command -v kubectl &>/dev/null; then
  kubectl kustomize -f "$KUSTOMIZATION"
else
  echo "FAIL: kustomize or kubectl required to build manifests" >&2
  exit 1
fi

echo "[deploy] build OK. Apply manually or via CI: kubectl apply -f - <(kustomize build -f $KUSTOMIZATION)"
