#!/usr/bin/env bash
# K8s 环境装配内部实现，只允许 stackctl 的受控环境入口调用。
# DEPLOY_ENV 必须由调用方设置（beta|gamma）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

DEPLOY_ENV="${DEPLOY_ENV:?DEPLOY_ENV must be set to beta or gamma}"
if [[ "$DEPLOY_ENV" != "beta" && "$DEPLOY_ENV" != "gamma" ]]; then
  echo "FAIL: DEPLOY_ENV must be beta or gamma, got: $DEPLOY_ENV" >&2
  exit 1
fi
export APP_RUNTIME_ENV="${DEPLOY_ENV}"
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/quwoquan_ops/gate/verify_domain_governance.py"
KUSTOMIZATION="quwoquan_ops/environments/${DEPLOY_ENV}"

if [[ ! -d "$KUSTOMIZATION" ]]; then
  echo "FAIL: kustomization not found: $KUSTOMIZATION" >&2
  exit 1
fi

echo "[deploy] ${DEPLOY_ENV} autonomous environment assembly"
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
