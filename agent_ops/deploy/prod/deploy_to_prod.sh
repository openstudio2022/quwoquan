#!/usr/bin/env bash
# 部署到 prod 环境，支持版本注入与 dry_run
# 用法: CLOUD_PROVIDER=aliyun IMAGE_VERSION=x CONFIG_VERSION=y REPLICAS=2 DRY_RUN=true agent_ops/deploy/prod/deploy_to_prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

CLOUD_PROVIDER="${CLOUD_PROVIDER:-aliyun}"
IMAGE_VERSION="${IMAGE_VERSION:-}"
CONFIG_VERSION="${CONFIG_VERSION:-}"
REPLICAS="${REPLICAS:-2}"
DRY_RUN="${DRY_RUN:-true}"
PROD_KUBECONFIG="${PROD_KUBECONFIG:-}"
SEED_BOX_IMAGE_REPOSITORY="${SEED_BOX_IMAGE_REPOSITORY:-ghcr.io/openstudio2022/quwoquan/seed-box}"
RECOMMENDATION_SERVICE_IMAGE_REPOSITORY="${RECOMMENDATION_SERVICE_IMAGE_REPOSITORY:-ghcr.io/openstudio2022/quwoquan/recommendation-service}"

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
  python3 - "$OVERLAY/kustomization.yaml" "$CONFIG_VERSION" "$IMAGE_VERSION" "$REPLICAS" "$SEED_BOX_IMAGE_REPOSITORY" "$RECOMMENDATION_SERVICE_IMAGE_REPOSITORY" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
config_version = sys.argv[2]
image_version = sys.argv[3]
replicas = sys.argv[4]
seed_box_repo = sys.argv[5]
recommendation_repo = sys.argv[6]
text = path.read_text(encoding="utf-8")
text = re.sub(r"CONFIG_VERSION=[^\s]*", f"CONFIG_VERSION={config_version}", text)
text = re.sub(r"IMAGE_VERSION=[^\s]*", f"IMAGE_VERSION={image_version}", text)
text = re.sub(r"REPLICAS=\d+", f"REPLICAS={replicas}", text)
text = re.sub(r"HPA_MIN_REPLICAS=\d+", f"HPA_MIN_REPLICAS={replicas}", text)
text = text.replace("name: ghcr.io/openstudio2022/quwoquan/seed-box", f"name: {seed_box_repo}")
text = text.replace(
    "name: ghcr.io/openstudio2022/quwoquan/recommendation-service",
    f"name: {recommendation_repo}",
)
text = re.sub(
    r"(name:\s*" + re.escape(seed_box_repo) + r"\s+newTag:\s*)[^\s]+",
    rf"\g<1>{image_version}",
    text,
    flags=re.MULTILINE,
)
text = re.sub(
    r"(name:\s*" + re.escape(recommendation_repo) + r"\s+newTag:\s*)[^\s]+",
    rf"\g<1>{image_version}",
    text,
    flags=re.MULTILINE,
)
path.write_text(text, encoding="utf-8")
PY
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
