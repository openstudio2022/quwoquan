#!/usr/bin/env bash
# K8s integration overlay 构建（beta/gamma 共用），由 deploy_beta_k8s.sh / deploy_gamma_k8s.sh 调用
# DEPLOY_ENV 必须由调用方设置（beta|gamma）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

DEPLOY_ENV="${DEPLOY_ENV:?DEPLOY_ENV must be set to beta or gamma}"
CLOUD_PROVIDER="${CLOUD_PROVIDER:-aliyun}"
KUSTOMIZATION="deploy/kustomization/${CLOUD_PROVIDER}-integration"

if [[ ! -d "$KUSTOMIZATION" ]]; then
  echo "FAIL: kustomization not found: $KUSTOMIZATION" >&2
  echo "CLOUD_PROVIDER must be one of: aliyun, volcengine, huaweicloud" >&2
  exit 1
fi

echo "[deploy] ${DEPLOY_ENV} integration (CLOUD_PROVIDER=$CLOUD_PROVIDER)"
echo "[deploy] building: $KUSTOMIZATION"

if command -v kustomize &>/dev/null; then
  kustomize build "$KUSTOMIZATION"
elif command -v kubectl &>/dev/null; then
  kubectl kustomize "$KUSTOMIZATION"
else
  echo "FAIL: kustomize or kubectl required to build manifests" >&2
  exit 1
fi

echo "[deploy] build OK (env=${DEPLOY_ENV}). Apply manually or via CI: kubectl apply -f - <(kustomize build $KUSTOMIZATION)"
