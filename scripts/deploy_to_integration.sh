#!/usr/bin/env bash
# 部署到 integration 环境，支持 CLOUD_PROVIDER 切换（aliyun|volcengine|huaweicloud）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLOUD_PROVIDER="${CLOUD_PROVIDER:-aliyun}"
OVERLAY_DIR="deploy/cloud-providers/${CLOUD_PROVIDER}/seed-box/overlays/integration"

if [[ ! -d "$OVERLAY_DIR" ]]; then
  echo "FAIL: overlay not found: $OVERLAY_DIR" >&2
  echo "CLOUD_PROVIDER must be one of: aliyun, volcengine, huaweicloud" >&2
  exit 1
fi

echo "[deploy] integration (CLOUD_PROVIDER=$CLOUD_PROVIDER)"
echo "[deploy] building: $OVERLAY_DIR"

if command -v kustomize &>/dev/null; then
  kustomize build "$OVERLAY_DIR"
elif command -v kubectl &>/dev/null; then
  kubectl kustomize "$OVERLAY_DIR"
else
  echo "FAIL: kustomize or kubectl required to build manifests" >&2
  exit 1
fi

echo "[deploy] build OK. Apply manually or via CI: kubectl apply -k $OVERLAY_DIR"
