#!/usr/bin/env bash
# 部署到 prod 环境，支持版本注入与 dry_run。
# Modular-monolith-first：seed-box 与 recommendation-service 各自独立 Deployment（同集群、同 namespace），
# 分别 patch 各自 overlay 并独立 rollout，不再以 sidecar 形式共用一个 Pod。
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
PROD_NAMESPACE="${PROD_NAMESPACE:-seed-box-prod}"
SEED_BOX_IMAGE_REPOSITORY="${SEED_BOX_IMAGE_REPOSITORY:-ghcr.io/openstudio2022/quwoquan/seed-box}"
RECOMMENDATION_SERVICE_IMAGE_REPOSITORY="${RECOMMENDATION_SERVICE_IMAGE_REPOSITORY:-ghcr.io/openstudio2022/quwoquan/recommendation-service}"

SEED_OVERLAY="$ROOT/deploy/service/seed-box/kustomize/overlays/prod"
REC_OVERLAY="$ROOT/deploy/service/recommendation-service/kustomize/overlays/prod"
KUSTOMIZATION="deploy/kustomization/${CLOUD_PROVIDER}-prod"

# rollout 目标来自三态 inventory（wired_to_prod_root=true）：
# Modular Monolith 单元（seed-box）+ 同集群独立 workload；Strangler 拆分新增的独立 workload
# 一旦在 inventory 中 wired，即自动纳入 rollout，无需改本脚本。
ROLLOUT_REFS="$(python3 - <<'PY'
import yaml
from pathlib import Path

inv = yaml.safe_load(Path("deploy/shared/workload_topology_inventory.yaml").read_text(encoding="utf-8"))
refs = []
for w in inv.get("workloads", []):
    if w.get("wired_to_prod_root"):
        kind = str(w.get("workload_resource", "Deployment")).lower()
        refs.append(f"{kind}/{w['name']}")
print(" ".join(refs))
PY
)"
if [[ -z "$ROLLOUT_REFS" ]]; then
  ROLLOUT_REFS="deployment/seed-box deployment/recommendation-service"
fi

if [[ ! -d "$KUSTOMIZATION" ]]; then
  echo "FAIL: kustomization not found: $KUSTOMIZATION" >&2
  exit 1
fi

prepare_prod_kubeconfig() {
  if [[ -z "$PROD_KUBECONFIG" ]]; then
    echo "::error::PROD_KUBECONFIG is required for real prod apply" >&2
    exit 2
  fi
  mkdir -p ~/.kube
  if ! PROD_KUBECONFIG="$PROD_KUBECONFIG" python3 - ~/.kube/config <<'PY'
import base64
import os
import sys
from pathlib import Path

raw = os.environ.get("PROD_KUBECONFIG", "").strip()
target = Path(sys.argv[1])
try:
    decoded = base64.b64decode(raw, validate=True).decode("utf-8")
except Exception as exc:  # noqa: BLE001
    print(f"::error::PROD_KUBECONFIG must be base64-encoded kubeconfig content: {exc}", file=sys.stderr)
    raise SystemExit(2)
required = ("apiVersion:", "clusters:", "contexts:", "users:")
missing = [item for item in required if item not in decoded]
if missing:
    print(
        "::error::PROD_KUBECONFIG decoded payload does not look like kubeconfig; missing: "
        + ", ".join(missing),
        file=sys.stderr,
    )
    raise SystemExit(2)
target.write_text(decoded, encoding="utf-8")
PY
  then
    rm -f ~/.kube/config
    exit 2
  fi
  chmod 600 ~/.kube/config
  if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "::error::PROD_KUBECONFIG cannot reach the prod cluster" >&2
    exit 2
  fi
}

patch_overlay() {
  # $1: overlay kustomization 文件; $2: 该 overlay 对应镜像仓库
  python3 - "$1" "$CONFIG_VERSION" "$IMAGE_VERSION" "$REPLICAS" "$2" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
config_version = sys.argv[2]
image_version = sys.argv[3]
replicas = sys.argv[4]
repo = sys.argv[5]
text = path.read_text(encoding="utf-8")
# 仅替换 configMap literal 行，避免误伤 HPA_MAX_REPLICAS 等其它字段。
text = re.sub(r"(?m)^(\s*-\s*)CONFIG_VERSION=\S*", rf"\g<1>CONFIG_VERSION={config_version}", text)
text = re.sub(r"(?m)^(\s*-\s*)IMAGE_VERSION=\S*", rf"\g<1>IMAGE_VERSION={image_version}", text)
text = re.sub(r"(?m)^(\s*-\s*)REPLICAS=\d+", rf"\g<1>REPLICAS={replicas}", text)
text = re.sub(r"(?m)^(\s*-\s*)HPA_MIN_REPLICAS=\d+", rf"\g<1>HPA_MIN_REPLICAS={replicas}", text)
text = re.sub(
    r"(name:\s*" + re.escape(repo) + r"\s+newTag:\s*)\S+",
    rf"\g<1>{image_version}",
    text,
)
path.write_text(text, encoding="utf-8")
PY
}

# 版本注入：若提供则 patch 两个 overlay（构建后由 trap 还原工作区）。
if [[ -n "$IMAGE_VERSION" && -n "$CONFIG_VERSION" ]]; then
  SEED_BACKUP="$(mktemp)"
  REC_BACKUP="$(mktemp)"
  cp "$SEED_OVERLAY/kustomization.yaml" "$SEED_BACKUP"
  cp "$REC_OVERLAY/kustomization.yaml" "$REC_BACKUP"
  trap "mv '$SEED_BACKUP' '$SEED_OVERLAY/kustomization.yaml'; mv '$REC_BACKUP' '$REC_OVERLAY/kustomization.yaml'" EXIT
  patch_overlay "$SEED_OVERLAY/kustomization.yaml" "$SEED_BOX_IMAGE_REPOSITORY"
  patch_overlay "$REC_OVERLAY/kustomization.yaml" "$RECOMMENDATION_SERVICE_IMAGE_REPOSITORY"
fi

echo "[deploy] prod (CLOUD_PROVIDER=$CLOUD_PROVIDER, DRY_RUN=$DRY_RUN, workloads=[$ROLLOUT_REFS])"

if [[ "$DRY_RUN" != "true" ]]; then
  prepare_prod_kubeconfig
fi

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
echo "$MANIFEST" | kubectl apply -f - --server-side
for ref in $ROLLOUT_REFS; do
  kubectl rollout status "$ref" -n "$PROD_NAMESPACE" --timeout=5m
done
