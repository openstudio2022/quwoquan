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
#   ROLLOUT_STAGE=gray-initial IMAGE_VERSION=<sha> CONFIG_VERSION=<cfg> quwoquan_ops/cli/prod/deploy_to_prod.sh
# 用法（真实发布）：
#   DRY_RUN=false ROLLOUT_STAGE=gray-initial IMAGE_VERSION=<sha> CONFIG_VERSION=<cfg> \
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
IMAGE_VERSION="${IMAGE_VERSION:-}"
CONFIG_VERSION="${CONFIG_VERSION:-}"
PREVIOUS_IMAGE_VERSION="${PREVIOUS_IMAGE_VERSION:-}"
RELEASE_MANIFEST="${RELEASE_MANIFEST:-}"
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

if [[ "$DRY_RUN" != "true" && -z "$PREVIOUS_IMAGE_VERSION" ]]; then
  echo "::error::真实发布必须显式提供 PREVIOUS_IMAGE_VERSION，禁止无旧版本回滚" >&2
  exit 2
fi
if [[ "$DRY_RUN" != "true" && "$PROD_IMAGE_DELIVERY_MODE" != "skip" && ! -s "$RELEASE_MANIFEST" ]]; then
  echo "::error::真实发布必须提供可部署的 RELEASE_MANIFEST，禁止按 tag 或本地 latest 发布" >&2
  exit 2
fi

# SSH 目标主机：默认取 prod/runtime.yaml 的 prod-hosted publicBases.api，可由 PROD_SSH_HOST 覆盖。
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
            "recommendation-service": "recommendation-service",
            "service-plane": "__all__",
        }
        target = alias.get(service_filter, service_filter)
        if target != "__all__":
            governed = [item for item in governed if item == target]
    rows.append("\t".join([
        str(p.get("plane")),
        str(p.get("account")),
        str(p.get("composeProjectRoot")),
        str(p.get("sshKeySecret")),
        ",".join(governed) or "-",
        ",".join(support) or "-",
        str(p.get("credentialsPath") or "-"),
    ]))
print("\n".join(rows))
PY
)"

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
  local plane="$1" account="$2" compose_root="$3" secret_name="$4" governed_csv="$5" support_csv="$6" credentials_root="$7"
  [[ "$governed_csv" == "-" ]] && governed_csv=""
  [[ "$support_csv" == "-" ]] && support_csv=""
  [[ "$credentials_root" == "-" ]] && credentials_root=""
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

  if [[ "$plane" == "service" || "$plane" == "edge" ]]; then
    local render_dir
    render_dir="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$plane" "$INSTANCE_SUFFIX" <<'PY'
import sys

from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

print(
    deployment_render_dir(
        "prod",
        target="prod-hosted",
        name=f"{sys.argv[1]}-{sys.argv[2]}",
    )
)
PY
)"
    if [[ "$DRY_RUN" == "true" ]]; then
      # Dry-run 是源码配置的发布计划预览，不得依赖或生成可删除的发布输出。
      # 真正渲染仍在下方非 dry-run 分支中校验 package/report/release provenance。
      echo "[dry_run] ${plane} plane would render verified package into: ${render_dir}"
      local image_load_args=(
        --plane "$plane"
        --host "$PROD_SSH_HOST"
        --key-dir "$PROD_SSH_KEY_DIR"
        --services "${governed_csv}"
        --image-version "$IMAGE_VERSION"
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
        --rollout-stage "$ROLLOUT_STAGE" \
        --config-version "$CONFIG_VERSION" \
        --image-version "$IMAGE_VERSION" \
        --output-dir "$render_dir" >/dev/null
      if [[ "$PROD_IMAGE_DELIVERY_MODE" == "skip" ]]; then
        echo "[skip] service plane image delivery skipped; assuming remote images are already prepared"
      elif [[ "$PROD_IMAGE_DELIVERY_MODE" == "prebuilt" ]]; then
        python3 quwoquan_ops/cli/prod/load_prod_plane_images.py \
          --plane "$plane" \
          --host "$PROD_SSH_HOST" \
          --key-dir "$PROD_SSH_KEY_DIR" \
          --services "${governed_csv}" \
          --image-version "$IMAGE_VERSION" \
          --release-manifest "$RELEASE_MANIFEST" \
          --platform linux/amd64
      else
        echo "::error::PROD_IMAGE_DELIVERY_MODE=${PROD_IMAGE_DELIVERY_MODE} is not allowed; production deploy cannot rebuild images" >&2
        exit 2
      fi
      bash quwoquan_ops/cli/prod/sync_prod_plane_stack.sh \
        --plane "$plane" \
        --host "$PROD_SSH_HOST" \
        --source-dir "$render_dir"
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
      \"\$repository:${IMAGE_VERSION}\"|\"\$repository:${PREVIOUS_IMAGE_VERSION}\") ;;
      \"\$repository:\"*) podman image rm \"\$image\" ;;
    esac
  done < <(podman images --format '{{.Repository}}:{{.Tag}}')
done
echo \"[plane ${plane}] retained exactly current/previous release image tags\""
  fi
  local remote_cmd
  remote_cmd="set -euo pipefail
cd '${compose_root}'
compose_file='docker-compose.prod-hosted.yaml'
env_file='stack.env'
export IMAGE_VERSION='${IMAGE_VERSION}' CONFIG_VERSION='${CONFIG_VERSION}' ROLLOUT_STAGE='${ROLLOUT_STAGE}'
${runtime_credential_preflight}
podman compose --env-file \"\$env_file\" -f \"\$compose_file\" -p '${project}' up -d --force-recreate --no-deps ${startup_services}
${image_retention}
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
    echo "::error::plane=${plane} 发布失败；由 stackctl 全平面事务统一回滚" >&2
    return 2
  fi
  echo "[plane ${plane}] deploy ok"
}

deploy_observability_stack() {
  local service_account="" service_root="" service_secret="" credentials_root=""
  while IFS=$'\t' read -r plane account compose_root secret_name _governed _support plane_credentials; do
    if [[ "$plane" == "service" ]]; then
      service_account="$account"
      service_root="$compose_root"
      service_secret="$secret_name"
      credentials_root="$plane_credentials"
      break
    fi
  done <<< "$PLANE_PLAN"
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
  local project="quwoquan-observability-prod"

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

  echo "----- plane=service observability project=${project} -----"
  if [[ "$DRY_RUN" == "true" ]]; then
    if resolve_plane_ssh "$service_secret" "$service_account" >/dev/null 2>&1; then
      echo "[dry_run] ssh ${service_account}@${PROD_SSH_HOST} (${RESOLVED_SSH_SOURCE}) <<observability>>"
    else
      echo "[dry_run] ssh ${service_account}@${PROD_SSH_HOST} (credential unresolved for ${service_secret}) <<observability>>"
    fi
    echo "$remote_cmd"
    return 0
  fi
  run_remote_bash "$service_account" "$service_secret" "$remote_cmd"
}

update_stable_gray_router() {
  local service_account="" service_root="" service_secret=""
  while IFS=$'\t' read -r plane account compose_root secret_name _governed _support _credentials; do
    if [[ "$plane" == "service" ]]; then
      service_account="$account"
      service_root="$compose_root"
      service_secret="$secret_name"
      break
    fi
  done <<< "$PLANE_PLAN"
  if [[ -z "$service_account" || -z "$service_root" || -z "$service_secret" ]]; then
    echo "::error::service plane is required to update the stable gray router" >&2
    return 2
  fi
  local render_dir
  render_dir="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

print(
    deployment_render_dir(
        "prod",
        target="prod-hosted",
        name="service-router-prod",
    )
)
PY
)"
  python3 quwoquan_ops/cli/prod/render_prod_plane_stack.py \
    --plane service \
    --instance prod \
    --rollout-stage "$ROLLOUT_STAGE" \
    --config-version "$CONFIG_VERSION" \
    --image-version "$IMAGE_VERSION" \
    --output-dir "$render_dir" >/dev/null
  bash quwoquan_ops/cli/prod/sync_prod_plane_stack.sh \
    --plane service \
    --host "$PROD_SSH_HOST" \
    --source-dir "$render_dir"
  local remote_cmd="set -euo pipefail
cd '${service_root}'
podman compose --env-file stack.env -f docker-compose.prod-hosted.yaml -p quwoquan-service-prod up -d --force-recreate --no-deps gamma-proxy
echo '[plane service] stable Caddy gray routing updated for ${ROLLOUT_STAGE}'"
  run_remote_bash "$service_account" "$service_secret" "$remote_cmd"
}

cleanup_gray_stacks() {
  while IFS=$'\t' read -r plane account compose_root secret_name _governed _support _credentials; do
    [[ -z "$plane" ]] && continue
    local project="quwoquan-${plane}-gray"
    local remote_cmd="set -euo pipefail
cd '${compose_root}'
podman compose --env-file stack.env -f docker-compose.prod-hosted.yaml -p '${project}' down --remove-orphans
echo '[plane ${plane}] removed completed gray stack ${project}'"
    run_remote_bash "$account" "$secret_name" "$remote_cmd"
  done <<< "$PLANE_PLAN"
}

while IFS=$'\t' read -r plane account compose_root secret_name governed_csv support_csv credentials_root; do
  [[ -z "$plane" ]] && continue
  deploy_plane "$plane" "$account" "$compose_root" "$secret_name" "$governed_csv" "$support_csv" "$credentials_root"
done <<< "$PLANE_PLAN"

deploy_observability_stack

if [[ "$DRY_RUN" != "true" && "$ROLLOUT_STAGE" != "full" ]]; then
  update_stable_gray_router
fi
if [[ "$DRY_RUN" != "true" && "$ROLLOUT_STAGE" == "full" ]]; then
  cleanup_gray_stacks
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[deploy] dry_run — 已预览各平面 SSH 发布计划，未执行。设置 DRY_RUN=false 并提供各平面 SSH 凭据后真实发布。"
fi
echo "[deploy] prod-hosted stage=$ROLLOUT_STAGE 完成（按平面账号隔离、gray-initial 承接远端验证）。"
