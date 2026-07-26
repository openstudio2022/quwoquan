#!/usr/bin/env bash
# K8s 环境装配入口构建，由 deploy_beta_k8s.sh / deploy_gamma_k8s.sh 调用。
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
bash "$ROOT/quwoquan_ops/cli/shared/verify_cdn_domain_injection.sh"
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
