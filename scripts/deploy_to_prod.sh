#!/usr/bin/env bash
# 部署到 prod 环境，支持版本注入与 dry_run
# 用法: CLOUD_PROVIDER=aliyun IMAGE_VERSION=x CONFIG_VERSION=y REPLICAS=2 DRY_RUN=true scripts/deploy_to_prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLOUD_PROVIDER="${CLOUD_PROVIDER:-aliyun}"
IMAGE_VERSION="${IMAGE_VERSION:-}"
CONFIG_VERSION="${CONFIG_VERSION:-}"
REPLICAS="${REPLICAS:-2}"
DRY_RUN="${DRY_RUN:-true}"
PROD_KUBECONFIG="${PROD_KUBECONFIG:-}"

OVERLAY="$ROOT/deploy/service/seed-box/kustomize/overlays/prod"
KUSTOMIZATION="deploy/kustomization/${CLOUD_PROVIDER}-prod"

if [[ ! -d "$KUSTOMIZATION" ]]; then
  echo "FAIL: kustomization not found: $KUSTOMIZATION" >&2
  exit 1
fi

# 版本注入：若提供则 patch overlay
if [[ -n "$IMAGE_VERSION" && -n "$CONFIG_VERSION" ]]; then
  BACKUP="$(mktemp)"
  cp "$OVERLAY/kustomization.yaml" "$BACKUP"
  trap "mv '$BACKUP' '$OVERLAY/kustomization.yaml'" EXIT
  sed -i.bak \
    -e "s/CONFIG_VERSION=[^[:space:]]*/CONFIG_VERSION=$CONFIG_VERSION/" \
    -e "s/IMAGE_VERSION=[^[:space:]]*/IMAGE_VERSION=$IMAGE_VERSION/" \
    -e "s/REPLICAS=[0-9]*/REPLICAS=$REPLICAS/" \
    -e "s/HPA_MIN_REPLICAS=[0-9]*/HPA_MIN_REPLICAS=$REPLICAS/" \
    -e "s/newTag: [^[:space:]]*/newTag: $IMAGE_VERSION/" \
    "$OVERLAY/kustomization.yaml"
  rm -f "$OVERLAY/kustomization.yaml.bak"
fi

echo "[deploy] prod (CLOUD_PROVIDER=$CLOUD_PROVIDER, DRY_RUN=$DRY_RUN)"

if command -v kustomize &>/dev/null; then
  MANIFEST="$(kustomize build "$KUSTOMIZATION")"
elif command -v kubectl &>/dev/null; then
  MANIFEST="$(kubectl kustomize "$KUSTOMIZATION")"
else
  echo "FAIL: kustomize or kubectl required" >&2
  exit 1
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[deploy] dry_run — build OK, skipping apply"
  echo "$MANIFEST" | head -30
  exit 0
fi

if [[ -z "$PROD_KUBECONFIG" ]]; then
  echo "::warning::PROD_KUBECONFIG not set — skipping apply"
  exit 0
fi

mkdir -p ~/.kube
echo "$PROD_KUBECONFIG" | base64 -d > ~/.kube/config
chmod 600 ~/.kube/config
echo "$MANIFEST" | kubectl apply -f - --server-side
kubectl rollout status deployment/seed-box -n seed-box-prod --timeout=5m
