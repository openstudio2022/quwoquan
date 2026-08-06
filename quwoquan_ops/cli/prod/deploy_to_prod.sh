#!/usr/bin/env bash
# 部署到 prod-hosted（远端唯一托管目标，backend=ssh-hosted，去 root）。
#
# 模型（与 quwoquan_ops/environments/prod/access-isolation.yaml 单一真相源一致）：
#   - 远端就是与原 gamma 同台的 ECS（SSH + rootless podman compose），非独立 k8s；PROD_KUBECONFIG 已退役。
#   - 按 edge/media/service/data 四平面隔离：每个读写平面用各自 Linux service 账号 prod-<plane>-svc 自登录，
#     仅操作本平面 governedWorkloads；data 平面只读审计，不参与 deploy。
#   - rollout stage：gray-initial（取同集群一个灰度实例验证，承接原远端 gamma 验证职责）-> carry-on -> full。
#   - 凭据：每平面独立 SSH key 逻辑 id（PROD_<PLANE>_SSH_KEY）；实际私钥只允许来自本机 key 文件 /
#     self-hosted runner 私有目录 / ssh-agent，禁止再把私钥正文注入 GitHub secrets。
#
# 用法（dry-run 预览，默认）：
#   ROLLOUT_STAGE=gray-initial IMAGE_TRANSPORT_TAG=<tag> CANDIDATE_DIGEST=<sha256> quwoquan_ops/cli/prod/deploy_to_prod.sh
# 用法（真实发布）：
#   DRY_RUN=false ROLLOUT_STAGE=gray-initial IMAGE_TRANSPORT_TAG=<tag> CANDIDATE_DIGEST=<sha256> \
#   PROD_SSH_KEY_DIR=~/.ssh/quwoquan-prod quwoquan_ops/cli/prod/deploy_to_prod.sh
#   或显式指定：
#   PROD_SERVICE_SSH_KEY_FILE=~/.ssh/quwoquan-prod/prod-service-svc quwoquan_ops/cli/prod/deploy_to_prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
PROD_DEPLOY_TARGET_ROOT="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_work_root

print(deployment_work_root("prod-hosted"))
PY
)"
QWQ_DEPLOY_WORK_ROOT="$(dirname "$PROD_DEPLOY_TARGET_ROOT")"
export QWQ_DEPLOY_WORK_ROOT

ACCESS_MANIFEST="quwoquan_ops/environments/prod/access-isolation.yaml"
TOPOLOGY_MANIFEST="quwoquan_ops/environments/prod/runtime.yaml"

DRY_RUN="${DRY_RUN:-true}"
ROLLOUT_STAGE="${ROLLOUT_STAGE:-gray-initial}"
IMAGE_TRANSPORT_TAG="${IMAGE_TRANSPORT_TAG:-}"
CANDIDATE_DIGEST="${CANDIDATE_DIGEST:-}"
PREVIOUS_IMAGE_TRANSPORT_TAG="${PREVIOUS_IMAGE_TRANSPORT_TAG:-}"
RELEASE_MANIFEST="${RELEASE_MANIFEST:-}"
RELEASE_EVIDENCE_DIGEST="${RELEASE_EVIDENCE_DIGEST:-}"
ROLLOUT_TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-300}"
PROD_SSH_KEY_DIR="${PROD_SSH_KEY_DIR:-$HOME/.ssh/quwoquan-prod}"
SERVICE_FILTER="${SERVICE:-}"
PROD_IMAGE_DELIVERY_MODE="${PROD_IMAGE_DELIVERY_MODE:-prebuilt}"

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

if [[ "$DRY_RUN" != "true" && -z "$PREVIOUS_IMAGE_TRANSPORT_TAG" ]]; then
  echo "::error::真实发布必须显式提供 PREVIOUS_IMAGE_TRANSPORT_TAG，禁止无旧候选回滚" >&2
  exit 2
fi
if [[ "$DRY_RUN" != "true" && ! "$RELEASE_EVIDENCE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "::error::真实发布必须提供 canonical RELEASE_EVIDENCE_DIGEST，配置 ACK 不允许脱离候选清单" >&2
  exit 2
fi
if [[ "$DRY_RUN" != "true" && "$PROD_IMAGE_DELIVERY_MODE" != "skip" && ! -s "$RELEASE_MANIFEST" ]]; then
  echo "::error::真实发布必须提供可部署的 RELEASE_MANIFEST，禁止按 tag 或本地 latest 发布" >&2
  exit 2
fi

# SSH 属于受限管理面，不得从面向 App 的 publicBases 推导。单主机
# PROD_SSH_HOST 仅保留为 break-glass 覆盖；常规发布从 access-isolation
# 的 management.hosts + deploymentInstances 解析全部 placement。
PROD_SSH_HOST="${PROD_SSH_HOST:-}"

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
  local host="$3"
  local remote_cmd="$4"
  resolve_plane_ssh "$secret_name" "$account"
  if [[ "$RESOLVED_SSH_USE_AGENT" == "true" ]]; then
    printf '%s\n' "$remote_cmd" | ssh \
      -o StrictHostKeyChecking=accept-new \
      -o BatchMode=yes \
      "${account}@${host}" \
      "bash -s"
    return $?
  fi
  printf '%s\n' "$remote_cmd" | ssh \
    -i "$RESOLVED_SSH_KEY_FILE" \
    -o StrictHostKeyChecking=accept-new \
    -o BatchMode=yes \
    "${account}@${host}" \
    "bash -s"
}

# 解析本 stage 的 host / deployment instance / replica 计划。输出只包含
# SSH credential 逻辑 id，不包含私钥或 Secret Bundle。
plan_args=(
  python3 quwoquan_ops/cli/prod/prod_hosted_topology.py
  --stage "$ROLLOUT_STAGE"
  --require-release-redundancy
  --format tsv
)
if [[ -n "$SERVICE_FILTER" ]]; then
  plan_args+=(--service-filter "$SERVICE_FILTER")
fi
if [[ -n "$PROD_SSH_HOST" ]]; then
  plan_args+=(--ssh-host "$PROD_SSH_HOST")
fi
PLANE_PLAN="$("${plan_args[@]}")"

if [[ -z "$PLANE_PLAN" ]]; then
  echo "FAIL: stage=$ROLLOUT_STAGE 未解析出任何读写平面（检查 $ACCESS_MANIFEST）" >&2
  exit 2
fi

# 灰度阶段始终只更新独立 gray 项目；full 才替换正式项目。
if [[ "$ROLLOUT_STAGE" == "gray-initial" || "$ROLLOUT_STAGE" == "carry-on" ]]; then
  INSTANCE_SUFFIX="gray"
else
  INSTANCE_SUFFIX="prod"
fi

echo "[deploy] prod-hosted stage=$ROLLOUT_STAGE instance=$INSTANCE_SUFFIX imageTransportTag=$IMAGE_TRANSPORT_TAG candidateDigest=$CANDIDATE_DIGEST DRY_RUN=$DRY_RUN"

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
  local plane="$1" account="$2" compose_root="$3" secret_name="$4" governed_csv="$5" support_csv="$6" credentials_root="$7"
  local host_id="$8" ssh_host="$9" replica_id="${10}" replica_count="${11}" remote_root="${12}" project="${13}" systemd_unit="${14}" render_name="${15}"
  [[ "$governed_csv" == "-" ]] && governed_csv=""
  [[ "$support_csv" == "-" ]] && support_csv=""
  [[ "$credentials_root" == "-" ]] && credentials_root=""
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

  if [[ "$plane" == "service" || "$plane" == "edge" ]]; then
    local render_dir
    render_dir="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$render_name" <<'PY'
import sys

from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

print(
    deployment_render_dir(
        "prod",
        target="prod-hosted",
        name=sys.argv[1],
    )
)
PY
)"
    if [[ "$DRY_RUN" == "true" ]]; then
      # Dry-run 是源码配置的发布计划预览，不得依赖或生成可删除的发布输出。
      # 真正渲染仍在下方非 dry-run 分支中校验 package/report/release provenance。
      echo "[dry_run] ${plane}/${replica_id} host=${host_id} would render verified package into: ${render_dir}"
      local image_load_args=(
        --plane "$plane"
        --host "$ssh_host"
        --key-dir "$PROD_SSH_KEY_DIR"
        --services "${governed_csv}"
        --image-transport-tag "$IMAGE_TRANSPORT_TAG"
        --platform linux/amd64
        --dry-run
      )
      if [[ -n "$RELEASE_MANIFEST" ]]; then
        image_load_args+=(--release-manifest "$RELEASE_MANIFEST")
      fi
      python3 quwoquan_ops/cli/prod/load_prod_plane_images.py \
        "${image_load_args[@]}"
    else
      python3 quwoquan_ops/cli/prod/render_prod_plane_stack.py \
        --plane "$plane" \
        --instance "$INSTANCE_SUFFIX" \
        --replica-id "$replica_id" \
        --host-id "$host_id" \
        --rollout-stage "$ROLLOUT_STAGE" \
        --candidate-digest "$CANDIDATE_DIGEST" \
        --image-transport-tag "$IMAGE_TRANSPORT_TAG" \
        --release-evidence-digest "$RELEASE_EVIDENCE_DIGEST" \
        --output-dir "$render_dir" \
        --host "$ssh_host" >/dev/null
      if [[ "$PROD_IMAGE_DELIVERY_MODE" == "skip" ]]; then
        echo "[skip] service plane image delivery skipped; assuming remote images are already prepared"
      elif [[ "$PROD_IMAGE_DELIVERY_MODE" == "prebuilt" ]]; then
        python3 quwoquan_ops/cli/prod/load_prod_plane_images.py \
          --plane "$plane" \
          --host "$ssh_host" \
          --key-dir "$PROD_SSH_KEY_DIR" \
          --services "${governed_csv}" \
          --image-transport-tag "$IMAGE_TRANSPORT_TAG" \
          --release-manifest "$RELEASE_MANIFEST" \
          --platform linux/amd64
      else
        echo "::error::PROD_IMAGE_DELIVERY_MODE=${PROD_IMAGE_DELIVERY_MODE} is not allowed; production deploy cannot rebuild images" >&2
        exit 2
      fi
      bash quwoquan_ops/cli/prod/sync_prod_plane_stack.sh \
        --plane "$plane" \
        --host "$ssh_host" \
        --source-dir "$render_dir" \
        --root-suffix "instances/${INSTANCE_SUFFIX}/${replica_id}"
    fi
  fi

  # 远端按平面账号执行：进入本平面 compose 项目根，按目标镜像版本拉起 governedWorkloads。
  local runtime_credential_preflight=""
  if [[ "$plane" == "service" && " $startup_services " == *" integration-service "* ]]; then
    runtime_credential_preflight="
credential_root='${credentials_root}'
if [[ \"\$credential_root\" != /* ]]; then
  echo \"FAIL: integration-service credentialsPath 必须是绝对路径\" >&2
  exit 2
fi
credential_dir=\"\$credential_root/integration\"
for dir in \"\$credential_root\" \"\$credential_dir\"; do
  if [[ ! -d \"\$dir\" || -L \"\$dir\" || ! -O \"\$dir\" ]]; then
    echo \"FAIL: integration-service 凭据目录缺失、不是当前账号所有或为符号链接: \$dir\" >&2
    exit 2
  fi
  if [[ \"\$(stat -c '%a' \"\$dir\")\" != \"700\" ]]; then
    echo \"FAIL: integration-service 凭据目录权限必须为 700: \$dir\" >&2
    exit 2
  fi
done
push_env=\"\$credential_dir/push.env\"
apns_key=\"\$credential_dir/apns-auth-key.p8\"
fcm_account=\"\$credential_dir/fcm-service-account.json\"
for path in \"\$push_env\" \"\$apns_key\" \"\$fcm_account\"; do
  if [[ ! -f \"\$path\" || -L \"\$path\" || ! -O \"\$path\" || ! -r \"\$path\" ]]; then
    echo \"FAIL: integration-service 凭据文件缺失、不可读、不是当前账号所有或为符号链接: \$path\" >&2
    exit 2
  fi
  case \"\$(stat -c '%a' \"\$path\")\" in
    400|600) ;;
    *)
      echo \"FAIL: integration-service 凭据文件权限必须为 400 或 600: \$path\" >&2
      exit 2
      ;;
  esac
done
for key in INTEGRATION_PUSH_APNS_KEY_ID INTEGRATION_PUSH_APNS_TEAM_ID INTEGRATION_PUSH_APNS_TOPIC INTEGRATION_PUSH_FCM_PROJECT_ID; do
  if ! awk -F= -v expected=\"\$key\" '\$1 == expected && length(substr(\$0, index(\$0, \"=\") + 1)) > 0 { found=1 } END { exit(found ? 0 : 1) }' \"\$push_env\"; then
    echo \"FAIL: integration-service push.env 缺少非空 \$key\" >&2
    exit 2
  fi
done
echo \"[plane service] integration push credentials preflight ok\""
  fi
  local image_retention=""
  if [[ "$ROLLOUT_STAGE" == "full" ]]; then
    image_retention="
for service in ${governed_services}; do
  repository=\"localhost/quwoquan_service_\${service}\"
  while IFS= read -r image; do
    case \"\$image\" in
      \"\$repository:${IMAGE_TRANSPORT_TAG}\"|\"\$repository:${PREVIOUS_IMAGE_TRANSPORT_TAG}\") ;;
      \"\$repository:\"*) podman image rm \"\$image\" ;;
    esac
  done < <(podman images --format '{{.Repository}}:{{.Tag}}')
done
echo \"[plane ${plane}] retained exactly current/previous release image tags\""
  fi
  local config_ack_wait=""
  if [[ "$plane" == "service" && " $startup_services " == *" platform-ops-service "* ]]; then
    config_ack_wait="
config_ack_deadline=\$((SECONDS + ${ROLLOUT_TIMEOUT_SECONDS}))
while true; do
  platform_container=\"\$(podman ps --filter \"label=com.docker.compose.project=${project}\" --filter 'label=com.docker.compose.service=platform-ops-service' --format '{{.ID}}' | awk 'NR == 1 { print; exit }')\"
  if [[ -n \"\$platform_container\" ]]; then
    config_ack_response=\"\$(podman exec \"\$platform_container\" wget -qO- http://127.0.0.1:18088/readyz/config-convergence 2>/dev/null || true)\"
    if [[ \"\$config_ack_response\" == *'\"status\":\"ready\"'* ]]; then
      echo \"[plane service] config ACK convergence ready\"
      break
    fi
  fi
  if (( SECONDS >= config_ack_deadline )); then
    echo \"FAIL: all governed service instances did not reach config ACK convergence within ${ROLLOUT_TIMEOUT_SECONDS}s\" >&2
    exit 2
  fi
  sleep 2
done"
  fi
  local remote_cmd
  remote_cmd="set -euo pipefail
cd '${remote_root}'
compose_file='docker-compose.prod-hosted.yaml'
env_file='stack.env'
export ROLLOUT_STAGE='${ROLLOUT_STAGE}'
${runtime_credential_preflight}
unit='${systemd_unit}'
unit_source=\"systemd/\$unit\"
unit_dir=\"\${XDG_CONFIG_HOME:-\$HOME/.config}/systemd/user\"
if [[ ! -f \"\$unit_source\" || -L \"\$unit_source\" || ! -r \"\$unit_source\" ]]; then
  echo \"FAIL: rootless runtime systemd unit is missing or unsafe: \$unit_source\" >&2
  exit 2
fi
install -d -m 700 \"\$unit_dir\"
install -m 600 \"\$unit_source\" \"\$unit_dir/\$unit\"
systemctl --user daemon-reload
systemctl --user enable \"\$unit\"
systemctl --user restart \"\$unit\"
systemctl --user is-enabled --quiet \"\$unit\"
systemctl --user is-active --quiet \"\$unit\"
${config_ack_wait}
${image_retention}
echo \"[plane ${plane}] rollout ok project=${project} unit=\$unit services=[${startup_services}]\""

  echo "----- plane=${plane} replica=${replica_id}/${replica_count} host=${host_id} account=${account} project=${project} -----"
  if [[ "$DRY_RUN" == "true" ]]; then
    if resolve_plane_ssh "$secret_name" "$account" >/dev/null 2>&1; then
      echo "[dry_run] ssh ${account}@${ssh_host} (${RESOLVED_SSH_SOURCE}) <<remote>>"
    else
      echo "[dry_run] ssh ${account}@${ssh_host} (credential unresolved for ${secret_name}) <<remote>>"
    fi
    echo "$remote_cmd"
    return 0
  fi

  if ! run_remote_bash "$account" "$secret_name" "$ssh_host" "$remote_cmd"; then
    echo "::error::plane=${plane} 发布失败；由 stackctl 全平面事务统一回滚" >&2
    return 2
  fi
  echo "[plane ${plane}] deploy ok"
}

deploy_observability_replica() {
  local service_account="$1" service_root="$2" service_secret="$3" credentials_root="$4"
  local ssh_host="$5" host_id="$6" replica_id="$7"
  if [[ -z "$service_account" || -z "$service_root" || -z "$service_secret" || -z "$credentials_root" || "$credentials_root" == "-" ]]; then
    echo "::error::service plane credentials are required for the observability stack" >&2
    return 2
  fi

  local runtime_plan
  runtime_plan="$(python3 - "$ACCESS_MANIFEST" <<'PY'
import re
import sys
from pathlib import PurePosixPath

import yaml

access = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
service = next(
    (
        plane
        for plane in (access.get("planes") or [])
        if isinstance(plane, dict) and plane.get("plane") == "service"
    ),
    None,
)
runtime = service.get("rootlessObservabilityRuntime") if isinstance(service, dict) else None
if not isinstance(runtime, dict):
    raise SystemExit("FAIL: service plane rootlessObservabilityRuntime is required")

directory = str(runtime.get("composeDirectory") or "")
compose_file = str(runtime.get("composeFile") or "")
systemd_unit_file = str(runtime.get("systemdUnitFile") or "")
runtime_env_file = str(runtime.get("runtimeEnvFile") or "")
credentials_env = str(runtime.get("credentialsEnvFile") or "")
for label, value in (
    ("composeDirectory", directory),
    ("composeFile", compose_file),
    ("systemdUnitFile", systemd_unit_file),
    ("runtimeEnvFile", runtime_env_file),
    ("credentialsEnvFile", credentials_env),
):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"FAIL: observability {label} must be a safe relative path")
if "/" in compose_file:
    raise SystemExit("FAIL: observability composeFile must be a file name")
if not systemd_unit_file.endswith(".service") or "/" in systemd_unit_file:
    raise SystemExit("FAIL: observability systemdUnitFile must be a service file name")

required = [str(item) for item in (runtime.get("requiredEnvironment") or [])]
if not required or any(re.fullmatch(r"[A-Z][A-Z0-9_]*", item) is None for item in required):
    raise SystemExit("FAIL: observability requiredEnvironment must contain uppercase variable names")
health_urls = [str(item) for item in (runtime.get("healthURLs") or [])]
if not health_urls or any(
    re.fullmatch(r"http://127\.0\.0\.1:[0-9]{2,5}/[-A-Za-z0-9_./]*", item) is None
    for item in health_urls
):
    raise SystemExit("FAIL: observability healthURLs must be localhost HTTP probes")
print("\t".join((directory, compose_file, systemd_unit_file, runtime_env_file, credentials_env, ",".join(required), ",".join(health_urls))))
PY
)"
  local observability_dir="" observability_compose="" systemd_unit_file="" runtime_env_relative="" credentials_env_relative="" required_environment="" health_urls=""
  IFS=$'\t' read -r observability_dir observability_compose systemd_unit_file runtime_env_relative credentials_env_relative required_environment health_urls <<< "$runtime_plan"
  local observability_env="${credentials_root%/}/${credentials_env_relative}"
  local project="quwoquan-observability-prod-${replica_id}"

  local remote_cmd
  remote_cmd="set -euo pipefail
cd '${service_root}'
observability_dir='${observability_dir}'
compose_file='${observability_compose}'
systemd_unit_file='${systemd_unit_file}'
runtime_env=\"\$observability_dir/${runtime_env_relative}\"
observability_env='${observability_env}'
if [[ ! -d \"\$observability_dir\" || -L \"\$observability_dir\" ]]; then
  echo \"FAIL: observability render directory is missing or symlinked: \$observability_dir\" >&2
  exit 2
fi
if [[ ! -f \"\$observability_dir/\$compose_file\" || -L \"\$observability_dir/\$compose_file\" ]]; then
  echo \"FAIL: observability compose file is missing or symlinked: \$observability_dir/\$compose_file\" >&2
  exit 2
fi
if [[ ! -f \"\$runtime_env\" || -L \"\$runtime_env\" || ! -r \"\$runtime_env\" ]]; then
  echo \"FAIL: observability runtime env is missing, unreadable, or symlinked: \$runtime_env\" >&2
  exit 2
fi
unit_source=\"\$observability_dir/systemd/\$systemd_unit_file\"
if [[ ! -f \"\$unit_source\" || -L \"\$unit_source\" || ! -r \"\$unit_source\" ]]; then
  echo \"FAIL: observability systemd unit is missing, unreadable, or symlinked: \$unit_source\" >&2
  exit 2
fi
if ! awk -F= '\$1 == \"PROD_SERVICE_NETWORK\" && \$2 ~ /^[a-z0-9][a-z0-9_.-]*\$/ && length(\$2) >= 2 && length(\$2) <= 63 { found=1 } END { exit(found ? 0 : 1) }' \"\$runtime_env\"; then
  echo \"FAIL: observability runtime env has no safe PROD_SERVICE_NETWORK\" >&2
  exit 2
fi
if [[ ! -f \"\$observability_env\" || -L \"\$observability_env\" || ! -O \"\$observability_env\" || ! -r \"\$observability_env\" ]]; then
  echo \"FAIL: observability credentials env is missing, unreadable, not owned, or symlinked: \$observability_env\" >&2
  exit 2
fi
case \"\$(stat -c '%a' \"\$observability_env\")\" in
  400|600) ;;
  *) echo \"FAIL: observability credentials env permission must be 400 or 600: \$observability_env\" >&2; exit 2 ;;
esac
for key in ${required_environment//,/ }; do
  if ! awk -F= -v expected=\"\$key\" '\$1 == expected && length(substr(\$0, index(\$0, \"=\") + 1)) > 0 { found=1 } END { exit(found ? 0 : 1) }' \"\$observability_env\"; then
    echo \"FAIL: observability credentials env misses non-empty \$key\" >&2
    exit 2
  fi
done
for key in OBSERVABILITY_PROMETHEUS_IMAGE OBSERVABILITY_ALERTMANAGER_IMAGE OBSERVABILITY_OTEL_COLLECTOR_IMAGE OBSERVABILITY_NODE_EXPORTER_IMAGE OBSERVABILITY_PODMAN_EXPORTER_IMAGE OBSERVABILITY_MONGODB_EXPORTER_IMAGE OBSERVABILITY_POSTGRES_EXPORTER_IMAGE OBSERVABILITY_REDIS_EXPORTER_IMAGE; do
  image=\"\$(awk -F= -v expected=\"\$key\" '\$1 == expected { print substr(\$0, index(\$0, \"=\") + 1); exit }' \"\$observability_env\")\"
  if [[ ! \"\$image\" =~ @sha256:[0-9a-f]{64}$ ]]; then
    echo \"FAIL: observability image must be immutable digest: \$key\" >&2
    exit 2
  fi
done
unit_dir=\"\${XDG_CONFIG_HOME:-\$HOME/.config}/systemd/user\"
install -d -m 700 \"\$unit_dir\"
install -m 600 \"\$unit_source\" \"\$unit_dir/\$systemd_unit_file\"
systemctl --user daemon-reload
systemctl --user enable --now \"\$systemd_unit_file\"
systemctl --user is-enabled --quiet \"\$systemd_unit_file\"
systemctl --user is-active --quiet \"\$systemd_unit_file\"
for health_url in ${health_urls//,/ }; do
  curl --fail --silent --show-error --max-time 10 \"\$health_url\" >/dev/null
done
python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen(\"http://127.0.0.1:9090/api/v1/targets\", timeout=10) as response:
    payload = json.load(response)
if payload.get(\"status\") != \"success\":
    raise SystemExit(\"FAIL: Prometheus targets readback was not successful\")
targets = ((payload.get(\"data\") or {}).get(\"activeTargets\") or [])
if not targets:
    raise SystemExit(\"FAIL: Prometheus has no active targets\")
down = [
    (item.get(\"labels\") or {}).get(\"job\", \"unknown\")
    for item in targets
    if item.get(\"health\") != \"up\"
]
if down:
    raise SystemExit(\"FAIL: Prometheus targets are not up: \" + \",\".join(sorted(set(down))))
PY
echo \"[plane service] observability stack ready project=${project}\""

  echo "----- plane=service replica=${replica_id} host=${host_id} observability project=${project} -----"
  if [[ "$DRY_RUN" == "true" ]]; then
    if resolve_plane_ssh "$service_secret" "$service_account" >/dev/null 2>&1; then
      echo "[dry_run] ssh ${service_account}@${ssh_host} (${RESOLVED_SSH_SOURCE}) <<observability>>"
    else
      echo "[dry_run] ssh ${service_account}@${ssh_host} (credential unresolved for ${service_secret}) <<observability>>"
    fi
    echo "$remote_cmd"
    return 0
  fi
  run_remote_bash "$service_account" "$service_secret" "$ssh_host" "$remote_cmd"
}

update_stable_gray_router_replica() {
  local service_account="$1" compose_root="$2" service_secret="$3"
  local ssh_host="$4" host_id="$5" replica_id="$6"
  local service_root="${compose_root%/}/instances/prod/${replica_id}"
  if [[ -z "$service_account" || -z "$service_root" || -z "$service_secret" ]]; then
    echo "::error::service plane is required to update the stable gray router" >&2
    return 2
  fi
  local render_dir
  render_dir="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$replica_id" <<'PY'
import sys

from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

print(
    deployment_render_dir(
        "prod",
        target="prod-hosted",
        name=f"service-prod-{sys.argv[1]}",
    )
)
PY
)"
  python3 quwoquan_ops/cli/prod/render_prod_plane_stack.py \
    --plane service \
    --instance prod \
    --replica-id "$replica_id" \
    --host-id "$host_id" \
    --host "$ssh_host" \
    --rollout-stage "$ROLLOUT_STAGE" \
    --candidate-digest "$CANDIDATE_DIGEST" \
    --image-transport-tag "$IMAGE_TRANSPORT_TAG" \
    --output-dir "$render_dir" >/dev/null
  bash quwoquan_ops/cli/prod/sync_prod_plane_stack.sh \
    --plane service \
    --host "$ssh_host" \
    --source-dir "$render_dir" \
    --root-suffix "instances/prod/${replica_id}"
  local remote_cmd="set -euo pipefail
cd '${service_root}'
podman compose --env-file stack.env -f docker-compose.prod-hosted.yaml -p quwoquan-service-prod-${replica_id} restart gamma-proxy
podman compose --env-file stack.env -f docker-compose.prod-hosted.yaml -p quwoquan-service-prod-${replica_id} ps gamma-proxy
echo '[plane service] stable Caddy gray routing updated for ${ROLLOUT_STAGE}'"
  run_remote_bash "$service_account" "$service_secret" "$ssh_host" "$remote_cmd"
}

cleanup_gray_stacks() {
  while IFS=$'\t' read -r plane account compose_root secret_name _governed _support _credentials host_id ssh_host replica_id _replica_count _remote_root _project _systemd_unit _render_name; do
    [[ -z "$plane" ]] && continue
    local project="quwoquan-${plane}-gray-${replica_id}"
    local gray_root="${compose_root%/}/instances/gray/${replica_id}"
    local remote_cmd="set -euo pipefail
cd '${gray_root}'
unit='quwoquan-${plane}-gray-${replica_id}.service'
if systemctl --user list-unit-files \"\$unit\" --no-legend 2>/dev/null | grep -q \"\$unit\"; then
  systemctl --user disable --now \"\$unit\"
fi
echo '[plane ${plane}] removed completed gray stack ${project}'"
    run_remote_bash "$account" "$secret_name" "$ssh_host" "$remote_cmd"
  done <<< "$PLANE_PLAN"
}

while IFS=$'\t' read -r plane account compose_root secret_name governed_csv support_csv credentials_root host_id ssh_host replica_id replica_count remote_root project systemd_unit render_name; do
  [[ -z "$plane" ]] && continue
  deploy_plane "$plane" "$account" "$compose_root" "$secret_name" "$governed_csv" "$support_csv" "$credentials_root" "$host_id" "$ssh_host" "$replica_id" "$replica_count" "$remote_root" "$project" "$systemd_unit" "$render_name"
done <<< "$PLANE_PLAN"

if [[ "$ROLLOUT_STAGE" == "full" ]]; then
  while IFS=$'\t' read -r plane account _compose_root secret_name _governed _support credentials_root host_id ssh_host replica_id _replica_count remote_root _project _systemd_unit _render_name; do
    [[ "$plane" == "service" ]] || continue
    deploy_observability_replica "$account" "$remote_root" "$secret_name" "$credentials_root" "$ssh_host" "$host_id" "$replica_id"
  done <<< "$PLANE_PLAN"
else
  echo "[skip] observability remains bound to stable prod replicas during gray rollout"
fi

if [[ "$DRY_RUN" != "true" && "$ROLLOUT_STAGE" != "full" ]]; then
  while IFS=$'\t' read -r plane account compose_root secret_name _governed _support _credentials host_id ssh_host replica_id _replica_count _remote_root _project _systemd_unit _render_name; do
    [[ "$plane" == "service" ]] || continue
    update_stable_gray_router_replica "$account" "$compose_root" "$secret_name" "$ssh_host" "$host_id" "$replica_id"
  done <<< "$PLANE_PLAN"
fi
if [[ "$DRY_RUN" != "true" && "$ROLLOUT_STAGE" == "full" ]]; then
  cleanup_gray_stacks
fi

placement_count="$(printf '%s\n' "$PLANE_PLAN" | awk 'NF {c++} END {print c+0}')"
host_count="$(printf '%s\n' "$PLANE_PLAN" | awk -F'\t' 'NF {print $8}' | sort -u | awk 'NF {c++} END {print c+0}')"
echo "[deploy] placementCoverage hosts=${host_count} planeReplicas=${placement_count} instance=${INSTANCE_SUFFIX}"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[deploy] dry_run — 已预览各平面 SSH 发布计划，未执行。设置 DRY_RUN=false 并提供各平面 SSH 凭据后真实发布。"
fi
echo "[deploy] prod-hosted stage=$ROLLOUT_STAGE 完成（按平面账号隔离、gray-initial 承接远端验证）。"
