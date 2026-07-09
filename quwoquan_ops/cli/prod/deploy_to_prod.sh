#!/usr/bin/env bash
# 部署到 prod-hosted（远端唯一托管目标，backend=ssh-hosted，去 root）。
#
# 模型（与 quwoquan_ops/environments/prod_plane_access_isolation.yaml 单一真相源一致）：
#   - 远端就是与原 gamma 同台的 ECS（SSH + rootless podman compose），非独立 k8s；PROD_KUBECONFIG 已退役。
#   - 按 edge/media/service/data 四平面隔离：每个读写平面用各自 Linux service 账号 prod-<plane>-svc 自登录，
#     仅操作本平面 governedWorkloads；data 平面只读审计，不参与 deploy。
#   - rollout stage：gray-initial（取同集群一个灰度实例验证，承接原远端 gamma 验证职责）-> carry-on -> full。
#   - 凭据：每平面独立 SSH key 逻辑 id（PROD_<PLANE>_SSH_KEY）；实际私钥只允许来自本机 key 文件 /
#     self-hosted runner 私有目录 / ssh-agent，禁止再把私钥正文注入 GitHub secrets。
#
# 用法（dry-run 预览，默认）：
#   ROLLOUT_STAGE=gray-initial IMAGE_VERSION=<sha> CONFIG_VERSION=<cfg> quwoquan_ops/cli/prod/deploy_to_prod.sh
# 用法（真实发布）：
#   DRY_RUN=false ROLLOUT_STAGE=gray-initial IMAGE_VERSION=<sha> CONFIG_VERSION=<cfg> \
#   PROD_SSH_KEY_DIR=~/.ssh/quwoquan-prod quwoquan_ops/cli/prod/deploy_to_prod.sh
#   或显式指定：
#   PROD_SERVICE_SSH_KEY_FILE=~/.ssh/quwoquan-prod/prod-service-svc quwoquan_ops/cli/prod/deploy_to_prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ACCESS_MANIFEST="quwoquan_ops/environments/prod_plane_access_isolation.yaml"
TOPOLOGY_MANIFEST="quwoquan_ops/environments/environment_topology_manifest.yaml"

DRY_RUN="${DRY_RUN:-true}"
ROLLOUT_STAGE="${ROLLOUT_STAGE:-gray-initial}"
IMAGE_VERSION="${IMAGE_VERSION:-}"
CONFIG_VERSION="${CONFIG_VERSION:-}"
PREVIOUS_IMAGE_VERSION="${PREVIOUS_IMAGE_VERSION:-}"
ROLLOUT_TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-300}"
PROD_SSH_KEY_DIR="${PROD_SSH_KEY_DIR:-$HOME/.ssh/quwoquan-prod}"
SERVICE_FILTER="${SERVICE:-}"
PROD_IMAGE_DELIVERY_MODE="${PROD_IMAGE_DELIVERY_MODE:-auto}"

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

agent_has_pubkey() {
  local pub_file="$1"
  [[ -S "${SSH_AUTH_SOCK:-}" ]] || return 1
  [[ -f "$pub_file" ]] || return 1
  local expected
  expected="$(awk '{print $1 " " $2}' "$pub_file" 2>/dev/null || true)"
  [[ -n "$expected" ]] || return 1
  ssh-add -L 2>/dev/null | awk '{print $1 " " $2}' | rg -Fx --quiet "$expected"
}

resolve_plane_ssh() {
  local secret_name="$1"
  local account="$2"
  local explicit_var_file="${secret_name}_FILE"
  local explicit_var_path="${secret_name}_PATH"
  local candidate="${!explicit_var_file:-${!explicit_var_path:-}}"
  local key_file=""
  local pub_file=""
  local source=""
  if [[ -n "$candidate" ]]; then
    key_file="$candidate"
    source="explicit-file"
  else
    key_file="${PROD_SSH_KEY_DIR%/}/${account}"
    source="key-dir-file"
  fi
  pub_file="${key_file}.pub"
  if [[ -f "$key_file" ]]; then
    RESOLVED_SSH_SOURCE="$source:$key_file"
    RESOLVED_SSH_KEY_FILE="$key_file"
    RESOLVED_SSH_USE_AGENT="false"
    return 0
  fi
  if agent_has_pubkey "$pub_file"; then
    RESOLVED_SSH_SOURCE="ssh-agent:$pub_file"
    RESOLVED_SSH_KEY_FILE=""
    RESOLVED_SSH_USE_AGENT="true"
    return 0
  fi
  echo "::error::plane credential missing for ${secret_name}: key_file=${key_file} pub_file=${pub_file}" >&2
  return 1
}

run_remote_bash() {
  local account="$1"
  local secret_name="$2"
  local remote_cmd="$3"
  resolve_plane_ssh "$secret_name" "$account"
  if [[ "$RESOLVED_SSH_USE_AGENT" == "true" ]]; then
    printf '%s\n' "$remote_cmd" | ssh \
      -o StrictHostKeyChecking=accept-new \
      -o BatchMode=yes \
      "${account}@${PROD_SSH_HOST}" \
      "bash -s"
    return $?
  fi
  printf '%s\n' "$remote_cmd" | ssh \
    -i "$RESOLVED_SSH_KEY_FILE" \
    -o StrictHostKeyChecking=accept-new \
    -o BatchMode=yes \
    "${account}@${PROD_SSH_HOST}" \
    "bash -s"
}

# 解析本 stage 适用的读写平面计划（account / composeRoot / secret / governed+support compose services）。
PLANE_PLAN="$(python3 - "$ACCESS_MANIFEST" "$ROLLOUT_STAGE" <<'PY'
import sys, yaml
access = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
stage = sys.argv[2]
service_filter = __import__("os").environ.get("SERVICE", "").strip()
rows = []
for p in access.get("planes") or []:
    if str(p.get("access")) != "read-write":
        continue
    if stage not in (p.get("appliesToStages") or []):
        continue
    governed = [str(item) for item in (p.get("rootlessGovernedComposeServices") or []) if str(item).strip()]
    support = [str(item) for item in (p.get("rootlessSupportComposeServices") or []) if str(item).strip()]
    if str(p.get("plane")) == "service" and service_filter:
        alias = {
            "recommendation-service": "rec-model-service",
            "service-plane": "__all__",
            "seed-box": "__all__",
        }
        target = alias.get(service_filter, service_filter)
        if target != "__all__":
            governed = [item for item in governed if item == target]
    rows.append("\t".join([
        str(p.get("plane")),
        str(p.get("account")),
        str(p.get("composeProjectRoot")),
        str(p.get("sshKeySecret")),
        ",".join(governed),
        ",".join(support),
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
if ! python3 quwoquan_ops/cli/prod/validate_prod_plane_credentials.py --stage "$ROLLOUT_STAGE"; then
  if [[ "$DRY_RUN" != "true" ]]; then
    echo "::error::prod 平面 SSH 凭据硬校验未通过，终止发布" >&2
    exit 2
  fi
  echo "::warning::dry-run：平面 SSH 凭据未就绪，仅预览发布计划（真实发布将硬失败）" >&2
fi

deploy_plane() {
  local plane="$1" account="$2" compose_root="$3" secret_name="$4" governed_csv="$5" support_csv="$6"
  local project="quwoquan-${plane}-${INSTANCE_SUFFIX}"
  local governed_services="${governed_csv//,/ }"
  local support_services="${support_csv//,/ }"
  local startup_services="$governed_services"
  if [[ -n "$support_services" ]]; then
    startup_services="$support_services $governed_services"
  fi
  if [[ -z "${governed_services// }" ]]; then
    echo "[skip] plane=${plane} 当前无可 rollout 的 rootless governed services"
    return 0
  fi

  if [[ "$plane" == "service" ]]; then
    local render_dir=".qwq_output/local/prod-plane-stack/service-${INSTANCE_SUFFIX}"
    python3 quwoquan_ops/cli/prod/render_prod_plane_stack.py \
      --plane service \
      --instance "$INSTANCE_SUFFIX" \
      --config-version "$CONFIG_VERSION" \
      --output-dir "$render_dir" >/dev/null
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "[dry_run] service plane render ready: ${render_dir}"
      python3 quwoquan_ops/cli/prod/load_prod_plane_images.py \
        --plane service \
        --host "$PROD_SSH_HOST" \
        --key-dir "$PROD_SSH_KEY_DIR" \
        --services "${governed_csv}" \
        --platform linux/amd64 \
        --dry-run
    else
      if [[ "$PROD_IMAGE_DELIVERY_MODE" == "skip" ]]; then
        echo "[skip] service plane image delivery skipped; assuming remote images are already prepared"
      elif [[ "$PROD_IMAGE_DELIVERY_MODE" == "remote-build" ]]; then
        bash quwoquan_ops/cli/prod/sync_prod_build_workspace.sh \
          --host "$PROD_SSH_HOST" \
          --key-dir "$PROD_SSH_KEY_DIR" \
          --services "${governed_csv}" >/dev/null
        bash quwoquan_ops/cli/prod/build_prod_plane_images_remote.sh \
          --host "$PROD_SSH_HOST" \
          --key-dir "$PROD_SSH_KEY_DIR" \
          --services "${governed_csv}"
      else
        if ! python3 quwoquan_ops/cli/prod/load_prod_plane_images.py \
          --plane service \
          --host "$PROD_SSH_HOST" \
          --key-dir "$PROD_SSH_KEY_DIR" \
          --services "${governed_csv}" \
          --platform linux/amd64 \
          --rebuild-if-needed; then
          echo "[fallback] local amd64 image delivery failed; switching to remote native build" >&2
          bash quwoquan_ops/cli/prod/sync_prod_build_workspace.sh \
            --host "$PROD_SSH_HOST" \
            --key-dir "$PROD_SSH_KEY_DIR" \
            --services "${governed_csv}" >/dev/null
          bash quwoquan_ops/cli/prod/build_prod_plane_images_remote.sh \
            --host "$PROD_SSH_HOST" \
            --key-dir "$PROD_SSH_KEY_DIR" \
            --services "${governed_csv}"
        fi
      fi
      bash quwoquan_ops/cli/prod/sync_prod_plane_stack.sh \
        --plane service \
        --host "$PROD_SSH_HOST" \
        --source-dir "$render_dir"
    fi
  fi

  # 远端按平面账号执行：进入本平面 compose 项目根，按目标镜像版本拉起 governedWorkloads。
  local remote_cmd
  remote_cmd="set -euo pipefail
cd '${compose_root}'
compose_file='docker-compose.prod-hosted.yaml'
env_file='stack.env'
export IMAGE_VERSION='${IMAGE_VERSION}' CONFIG_VERSION='${CONFIG_VERSION}' ROLLOUT_STAGE='${ROLLOUT_STAGE}'
podman compose --env-file \"\$env_file\" -f \"\$compose_file\" -p '${project}' up -d --force-recreate --no-deps ${startup_services}
echo \"[plane ${plane}] rollout ok project=${project} services=[${startup_services}]\""

  echo "----- plane=${plane} account=${account} project=${project} -----"
  if [[ "$DRY_RUN" == "true" ]]; then
    if resolve_plane_ssh "$secret_name" "$account" >/dev/null 2>&1; then
      echo "[dry_run] ssh ${account}@${PROD_SSH_HOST} (${RESOLVED_SSH_SOURCE}) <<remote>>"
    else
      echo "[dry_run] ssh ${account}@${PROD_SSH_HOST} (credential unresolved for ${secret_name}) <<remote>>"
    fi
    echo "$remote_cmd"
    return 0
  fi

  if ! run_remote_bash "$account" "$secret_name" "$remote_cmd"; then
    echo "::error::plane=${plane} 发布失败，尝试回滚到 PREVIOUS_IMAGE_VERSION=${PREVIOUS_IMAGE_VERSION}" >&2
    rollback_plane "$plane" "$account" "$compose_root" "$secret_name" "$governed_csv"
    exit 2
  fi
  echo "[plane ${plane}] deploy ok"
}

rollback_plane() {
  local plane="$1" account="$2" compose_root="$3" secret_name="$4" workloads_csv="$5"
  local project="quwoquan-${plane}-${INSTANCE_SUFFIX}"
  local services="${workloads_csv//,/ }"
  if [[ -z "$PREVIOUS_IMAGE_VERSION" ]]; then
    echo "::warning::plane=${plane} 无 PREVIOUS_IMAGE_VERSION，跳过自动回滚（需人工介入）" >&2
    return 0
  fi
  local remote_cmd
  remote_cmd="set -euo pipefail
cd '${compose_root}'
compose_file='docker-compose.prod-hosted.yaml'
env_file='stack.env'
export IMAGE_VERSION='${PREVIOUS_IMAGE_VERSION}' ROLLOUT_STAGE='${ROLLOUT_STAGE}'
podman compose --env-file \"\$env_file\" -f \"\$compose_file\" -p '${project}' up -d --force-recreate --remove-orphans ${services}
echo \"[plane ${plane}] rolled back to ${PREVIOUS_IMAGE_VERSION}\""
  run_remote_bash "$account" "$secret_name" "$remote_cmd" || echo "::error::plane=${plane} 回滚也失败，需人工介入" >&2
}

while IFS=$'\t' read -r plane account compose_root secret_name governed_csv support_csv; do
  [[ -z "$plane" ]] && continue
  deploy_plane "$plane" "$account" "$compose_root" "$secret_name" "$governed_csv" "$support_csv"
done <<< "$PLANE_PLAN"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[deploy] dry_run — 已预览各平面 SSH 发布计划，未执行。设置 DRY_RUN=false 并提供各平面 SSH 凭据后真实发布。"
fi
echo "[deploy] prod-hosted stage=$ROLLOUT_STAGE 完成（按平面账号隔离、gray-initial 承接远端验证）。"
