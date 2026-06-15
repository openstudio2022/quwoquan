#!/usr/bin/env bash
# 部署到 prod-hosted（远端唯一托管目标，backend=ssh-hosted，去 root）。
#
# 模型（与 deploy/shared/prod_plane_access_isolation.yaml 单一真相源一致）：
#   - 远端就是与原 gamma 同台的 ECS（SSH + rootless podman compose），非独立 k8s；PROD_KUBECONFIG 已退役。
#   - 按 edge/media/service/data 四平面隔离：每个读写平面用各自 Linux service 账号 prod-<plane>-svc 自登录，
#     仅操作本平面 governedWorkloads；data 平面只读审计，不参与 deploy。
#   - rollout stage：gray-initial（取同集群一个灰度实例验证，承接原远端 gamma 验证职责）-> carry-on -> full。
#   - 凭据：每平面独立 SSH key secret PROD_<PLANE>_SSH_KEY，部署前硬校验，缺失即硬失败（禁止失败放通）。
#
# 用法（dry-run 预览，默认）：
#   ROLLOUT_STAGE=gray-initial IMAGE_VERSION=<sha> CONFIG_VERSION=<cfg> agent_ops/deploy/prod/deploy_to_prod.sh
# 用法（真实发布）：
#   DRY_RUN=false ROLLOUT_STAGE=gray-initial IMAGE_VERSION=<sha> CONFIG_VERSION=<cfg> \
#   PROD_EDGE_SSH_KEY=... PROD_MEDIA_SSH_KEY=... PROD_SERVICE_SSH_KEY=... agent_ops/deploy/prod/deploy_to_prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ACCESS_MANIFEST="deploy/shared/prod_plane_access_isolation.yaml"
TOPOLOGY_MANIFEST="deploy/shared/environment_topology_manifest.yaml"

DRY_RUN="${DRY_RUN:-true}"
ROLLOUT_STAGE="${ROLLOUT_STAGE:-gray-initial}"
IMAGE_VERSION="${IMAGE_VERSION:-}"
CONFIG_VERSION="${CONFIG_VERSION:-}"
PREVIOUS_IMAGE_VERSION="${PREVIOUS_IMAGE_VERSION:-}"
ROLLOUT_TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-300}"

case "$ROLLOUT_STAGE" in
  gray-initial|carry-on|full) ;;
  *) echo "FAIL: ROLLOUT_STAGE 必须为 gray-initial|carry-on|full，实际 $ROLLOUT_STAGE" >&2; exit 2 ;;
esac

if [[ ! -f "$ACCESS_MANIFEST" ]]; then
  echo "FAIL: 缺少访问隔离映射 $ACCESS_MANIFEST" >&2
  exit 2
fi

# 退役保险：彻底禁止 PROD_KUBECONFIG 复活。
if [[ -n "${PROD_KUBECONFIG:-}" ]]; then
  echo "::error::PROD_KUBECONFIG 已退役；prod 改为按平面 SSH 发布，请勿注入该 secret" >&2
  exit 2
fi

# SSH 目标主机：默认取 topology prod-hosted publicBases.api 的 host，可由 PROD_SSH_HOST 覆盖。
PROD_SSH_HOST="${PROD_SSH_HOST:-$(python3 - "$TOPOLOGY_MANIFEST" <<'PY'
import sys, yaml
from urllib.parse import urlparse
m = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
api = (((m.get("targets") or {}).get("prod-hosted") or {}).get("publicBases") or {}).get("api", "")
print(urlparse(api).hostname or "")
PY
)}"
if [[ -z "$PROD_SSH_HOST" ]]; then
  echo "FAIL: 无法解析 prod SSH host（设置 PROD_SSH_HOST 或修正 topology prod-hosted.publicBases.api）" >&2
  exit 2
fi

# 解析本 stage 适用的读写平面计划（account / host / composeRoot / secret / workloads）。
PLANE_PLAN="$(python3 - "$ACCESS_MANIFEST" "$ROLLOUT_STAGE" <<'PY'
import sys, yaml
access = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
stage = sys.argv[2]
rows = []
for p in access.get("planes") or []:
    if str(p.get("access")) != "read-write":
        continue
    if stage not in (p.get("appliesToStages") or []):
        continue
    workloads = ",".join(p.get("governedWorkloads") or [])
    rows.append("\t".join([
        str(p.get("plane")),
        str(p.get("account")),
        str(p.get("composeProjectRoot")),
        str(p.get("sshKeySecret")),
        workloads,
    ]))
print("\n".join(rows))
PY
)"

if [[ -z "$PLANE_PLAN" ]]; then
  echo "FAIL: stage=$ROLLOUT_STAGE 未解析出任何读写平面（检查 $ACCESS_MANIFEST）" >&2
  exit 2
fi

# 灰度实例命名：gray-initial 走独立 compose 项目命名空间，full/carry-on 走正式项目。
if [[ "$ROLLOUT_STAGE" == "gray-initial" ]]; then
  INSTANCE_SUFFIX="gray"
else
  INSTANCE_SUFFIX="prod"
fi

echo "[deploy] prod-hosted host=$PROD_SSH_HOST stage=$ROLLOUT_STAGE instance=$INSTANCE_SUFFIX image=$IMAGE_VERSION config=$CONFIG_VERSION DRY_RUN=$DRY_RUN"

# 凭据硬校验（缺失/非法即硬失败，禁止失败放通）。
# 真实发布（DRY_RUN=false）必须硬失败；dry-run 预览给出告警但仍展示发布计划。
if ! python3 agent_ops/deploy/prod/validate_prod_plane_credentials.py --stage "$ROLLOUT_STAGE"; then
  if [[ "$DRY_RUN" != "true" ]]; then
    echo "::error::prod 平面 SSH 凭据硬校验未通过，终止发布" >&2
    exit 2
  fi
  echo "::warning::dry-run：平面 SSH 凭据未就绪，仅预览发布计划（真实发布将硬失败）" >&2
fi

deploy_plane() {
  local plane="$1" account="$2" compose_root="$3" secret_name="$4" workloads_csv="$5"
  local project="quwoquan-${plane}-${INSTANCE_SUFFIX}"
  local services="${workloads_csv//,/ }"

  # 远端按平面账号执行：进入本平面 compose 项目根，按目标镜像版本拉起 governedWorkloads。
  local remote_cmd
  remote_cmd="set -euo pipefail
cd '${compose_root}'
export IMAGE_VERSION='${IMAGE_VERSION}' CONFIG_VERSION='${CONFIG_VERSION}' ROLLOUT_STAGE='${ROLLOUT_STAGE}'
podman compose -p '${project}' pull ${services}
podman compose -p '${project}' up -d ${services}
# rollout 等待：逐个 service 等待 healthy（compose healthcheck 为真相源）。
deadline=\$(( \$(date +%s) + ${ROLLOUT_TIMEOUT_SECONDS} ))
for svc in ${services}; do
  while :; do
    state=\$(podman inspect -f '{{.State.Health.Status}}' \"${project}_\${svc}_1\" 2>/dev/null || echo unknown)
    [ \"\$state\" = healthy ] && break
    [ \"\$state\" = unknown ] && break
    [ \$(date +%s) -ge \$deadline ] && { echo \"::error::rollout timeout svc=\$svc state=\$state\"; exit 2; }
    sleep 3
  done
done
echo \"[plane ${plane}] rollout ok project=${project} services=[${services}]\""

  echo "----- plane=${plane} account=${account} project=${project} -----"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry_run] ssh ${account}@${PROD_SSH_HOST} (key from ${secret_name}) <<remote>>"
    echo "$remote_cmd"
    return 0
  fi

  local key_value="${!secret_name:-}"
  if [[ -z "$key_value" ]]; then
    echo "::error::plane=${plane} 缺少 SSH 凭据 ${secret_name}" >&2
    exit 2
  fi
  local key_file
  key_file="$(mktemp)"
  chmod 600 "$key_file"
  printf '%s\n' "$key_value" > "$key_file"
  # shellcheck disable=SC2064
  trap "rm -f '$key_file'" RETURN

  if ! printf '%s\n' "$remote_cmd" | ssh \
      -i "$key_file" \
      -o StrictHostKeyChecking=accept-new \
      "${account}@${PROD_SSH_HOST}" \
      "bash -s"; then
    echo "::error::plane=${plane} 发布失败，尝试回滚到 PREVIOUS_IMAGE_VERSION=${PREVIOUS_IMAGE_VERSION}" >&2
    rollback_plane "$plane" "$account" "$compose_root" "$key_file" "$workloads_csv"
    exit 2
  fi
  echo "[plane ${plane}] deploy ok"
}

rollback_plane() {
  local plane="$1" account="$2" compose_root="$3" key_file="$4" workloads_csv="$5"
  local project="quwoquan-${plane}-${INSTANCE_SUFFIX}"
  local services="${workloads_csv//,/ }"
  if [[ -z "$PREVIOUS_IMAGE_VERSION" ]]; then
    echo "::warning::plane=${plane} 无 PREVIOUS_IMAGE_VERSION，跳过自动回滚（需人工介入）" >&2
    return 0
  fi
  local remote_cmd
  remote_cmd="set -euo pipefail
cd '${compose_root}'
export IMAGE_VERSION='${PREVIOUS_IMAGE_VERSION}' ROLLOUT_STAGE='${ROLLOUT_STAGE}'
podman compose -p '${project}' up -d ${services}
echo \"[plane ${plane}] rolled back to ${PREVIOUS_IMAGE_VERSION}\""
  printf '%s\n' "$remote_cmd" | ssh \
    -i "$key_file" \
    -o StrictHostKeyChecking=accept-new \
    "${account}@${PROD_SSH_HOST}" \
    "bash -s" || echo "::error::plane=${plane} 回滚也失败，需人工介入" >&2
}

while IFS=$'\t' read -r plane account compose_root secret_name workloads_csv; do
  [[ -z "$plane" ]] && continue
  deploy_plane "$plane" "$account" "$compose_root" "$secret_name" "$workloads_csv"
done <<< "$PLANE_PLAN"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[deploy] dry_run — 已预览各平面 SSH 发布计划，未执行。设置 DRY_RUN=false 并提供各平面 SSH 凭据后真实发布。"
fi
echo "[deploy] prod-hosted stage=$ROLLOUT_STAGE 完成（按平面账号隔离、gray-initial 承接远端验证）。"
