#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
LOCAL_GAMMA_ACTIVE_CHILD_PID=""

cleanup_active_child() {
  local exit_status="$?"
  if [[ -n "$LOCAL_GAMMA_ACTIVE_CHILD_PID" ]] \
    && kill -0 "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1; then
    echo "[local-gamma] stopping active child before exit" >&2
    kill "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1 || true
    wait "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1 || true
  fi
  LOCAL_GAMMA_ACTIVE_CHILD_PID=""
  trap - EXIT INT TERM HUP
  exit "$exit_status"
}
trap cleanup_active_child EXIT INT TERM HUP

QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
QWQ_LOCAL_RELEASE_ENV="${QWQ_LOCAL_RELEASE_ENV:-gamma}"
QWQ_LOCAL_RELEASE_TARGET="${QWQ_LOCAL_RELEASE_TARGET:-${QWQ_LOCAL_RELEASE_ENV}-local}"
if [[ "$QWQ_LOCAL_RELEASE_ENV" != "alpha" \
   && "$QWQ_LOCAL_RELEASE_ENV" != "beta" \
   && "$QWQ_LOCAL_RELEASE_ENV" != "gamma" ]]; then
  echo "[local-release] GATE_BLOCK: unsupported environment $QWQ_LOCAL_RELEASE_ENV" >&2
  exit 2
fi
if [[ "$QWQ_LOCAL_RELEASE_TARGET" != "${QWQ_LOCAL_RELEASE_ENV}-local" ]]; then
  echo "[local-release] GATE_BLOCK: target does not belong to environment" >&2
  exit 2
fi
export QWQ_LOCAL_RELEASE_ENV QWQ_LOCAL_RELEASE_TARGET
PRODUCT_TELEMETRY_AVAILABLE="${QWQ_PRODUCT_TELEMETRY_AVAILABLE:-1}"
WORKLOAD="${QWQ_WORKLOAD:-full}"
case "$WORKLOAD" in
  content-release)
    # Content import/API/media are intentionally independent from commercial
    # telemetry.  The release profile validates telemetry separately.
    PRODUCT_TELEMETRY_AVAILABLE=0
    filtered_profiles_csv=""
    requested_profiles_csv="${COMPOSE_PROFILES:-}"
    while IFS= read -r profile; do
      case "$profile" in
        ""|commercial-observability|assistant-runtime) ;;
        *)
          filtered_profiles_csv="${filtered_profiles_csv:+${filtered_profiles_csv},}${profile}"
          ;;
      esac
    done < <(printf '%s\n' "$requested_profiles_csv" | tr ',' '\n')
    COMPOSE_PROFILES="$filtered_profiles_csv"
    export COMPOSE_PROFILES
    ;;
  full)
    if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
      echo "[local-gamma] GATE_BLOCK: full workload requires product telemetry" >&2
      exit 2
    fi
    export COMPOSE_PROFILES="${COMPOSE_PROFILES:+${COMPOSE_PROFILES},}commercial-observability,assistant-runtime,edge-media"
    ;;
  *)
    echo "[local-gamma] FAIL: QWQ_WORKLOAD must be content-release or full" >&2
    exit 2
    ;;
esac
LOCAL_RUN_ACTION="up"
for arg in "$@"; do
  if [[ "$arg" == "--down" ]]; then LOCAL_RUN_ACTION="down"; fi
done
eval "$(python3 "$ROOT/quwoquan_ops/cli/lib/local_run.py" \
  --env "$QWQ_LOCAL_RELEASE_ENV" --target "$QWQ_LOCAL_RELEASE_TARGET" \
  --action "$LOCAL_RUN_ACTION" --output-root "$QWQ_OUTPUT_ROOT")"
export QWQ_OUTPUT_ROOT QWQ_DEPLOY_WORK_ROOT QWQ_OBSERVABILITY_RUN_ROOT QWQ_RUN_ROOT
COMPOSE_FILE="$ROOT/quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
COMPOSE_FILES=("$COMPOSE_FILE")
while IFS= read -r service_compose_file; do
  COMPOSE_FILES+=("$service_compose_file")
done < <(find "$ROOT/quwoquan_service/services" -mindepth 3 -maxdepth 3 -path '*/deploy/compose.yaml' -type f | sort)
while IFS= read -r service_environment_compose_file; do
  COMPOSE_FILES+=("$service_environment_compose_file")
done < <(find "$ROOT/quwoquan_service/services" -mindepth 5 -maxdepth 5 -path "*/environments/${QWQ_LOCAL_RELEASE_ENV}/deploy/compose.yaml" -type f | sort)
COMPOSE_FILES+=("$ROOT/quwoquan_service/control-plane/platform-ops/deploy/compose.yaml")
COMPOSE_FILE_ARGS=()
for service_compose_file in "${COMPOSE_FILES[@]}"; do
  COMPOSE_FILE_ARGS+=(-f "$service_compose_file")
done
if [[ "$QWQ_LOCAL_RELEASE_ENV" == "gamma" ]]; then
  default_compose_project="quwoquan_service"
else
  default_compose_project="quwoquan_${QWQ_LOCAL_RELEASE_ENV}_release"
fi
LOCAL_GAMMA_COMPOSE_PROJECT_NAME="${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:-$default_compose_project}"
LOCAL_GAMMA_REC_POLICY_SOURCE="$ROOT/quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
export LOCAL_GAMMA_REC_POLICY_SOURCE
if [[ -z "${LOCAL_GAMMA_HTTP_PORT:-}" \
   || -z "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_PLATFORM_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-}" \
   || -z "${LOCAL_GAMMA_CONTENT_PORT:-}" \
   || -z "${LOCAL_GAMMA_CHAT_PORT:-}" \
   || -z "${LOCAL_GAMMA_USER_PORT:-}" \
   || -z "${LOCAL_GAMMA_ASSISTANT_PORT:-}" \
   || -z "${LOCAL_GAMMA_REC_MODEL_PORT:-}" \
   || -z "${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-}" \
   || -z "${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-}" \
   || -z "${LOCAL_GAMMA_TAG_PORT:-}" \
   || -z "${LOCAL_GAMMA_SEARCH_PORT:-}" \
   || -z "${LOCAL_GAMMA_ENTITY_PORT:-}" \
   || -z "${LOCAL_GAMMA_CIRCLE_PORT:-}" \
   || -z "${LOCAL_GAMMA_INTEGRATION_PORT:-}" \
   || -z "${LOCAL_GAMMA_NOTIFICATION_PORT:-}" \
   || -z "${LOCAL_GAMMA_POSTGRES_PORT:-}" \
   || -z "${LOCAL_GAMMA_MONGO_PORT:-}" \
   || -z "${LOCAL_GAMMA_REDIS_PORT:-}" \
   || -z "${LOCAL_GAMMA_ES_PORT:-}" ]]; then
  eval "$(python3 "$ROOT/quwoquan_ops/cli/print_local_port_profile.py" --profile "$QWQ_LOCAL_RELEASE_TARGET" --format shell-defaults)"
fi
# docker compose 只读取导出的环境变量；这里把 canonical local-gamma 端口全部导出，
# 避免直接运行脚本/Makefile 时回退到 compose 文件里的旧默认端口。
export \
  LOCAL_GAMMA_HTTP_PORT \
  LOCAL_GAMMA_PRODUCT_OPS_PORT \
  LOCAL_GAMMA_PLATFORM_OPS_PORT \
  LOCAL_GAMMA_MEDIA_EDGE_PORT \
  LOCAL_GAMMA_CONTENT_PORT \
  LOCAL_GAMMA_CHAT_PORT \
  LOCAL_GAMMA_USER_PORT \
  LOCAL_GAMMA_ASSISTANT_PORT \
  LOCAL_GAMMA_REC_MODEL_PORT \
  LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT \
  LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT \
  LOCAL_GAMMA_TAG_PORT \
  LOCAL_GAMMA_SEARCH_PORT \
  LOCAL_GAMMA_ENTITY_PORT \
  LOCAL_GAMMA_CIRCLE_PORT \
  LOCAL_GAMMA_INTEGRATION_PORT \
  LOCAL_GAMMA_NOTIFICATION_PORT \
  LOCAL_GAMMA_POSTGRES_PORT \
  LOCAL_GAMMA_MONGO_PORT \
  LOCAL_GAMMA_MONGO_CACHE_SIZE_GB \
  LOCAL_GAMMA_REDIS_PORT \
  LOCAL_GAMMA_ES_PORT

export_service_compose_environment() {
  local source_name target_name
  export QWQ_COMPOSE_ENV="$QWQ_LOCAL_RELEASE_ENV"
  while IFS= read -r source_name; do
    # gamma-local infrastructure Compose still owns LOCAL_GAMMA_* mount/port
    # variables (for example the immutable Caddyfile source). Export both the
    # source name and its service-owned QWQ_COMPOSE alias.
    export "$source_name"
    target_name="QWQ_COMPOSE_${source_name#LOCAL_GAMMA_}"
    printf -v "$target_name" '%s' "${!source_name}"
    export "$target_name"
  done < <(compgen -A variable LOCAL_GAMMA_ | sort)
}
first_party_image_owners() {
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names

print("\n".join(first_party_service_names()))
PY
}
CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-}"
if [[ ! "$CONFIG_VERSION" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "[local-release] GATE_BLOCK: LOCAL_GAMMA_CONFIG_VERSION must be the canonical sha256 runtime configuration digest" >&2
  exit 2
fi
IMAGE_VERSION="${LOCAL_GAMMA_IMAGE_VERSION:-}"
eval "$(
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import shlex
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

import os

bases = get_target(
    load_environment_topology(), os.environ["QWQ_LOCAL_RELEASE_TARGET"]
)["publicBases"]
for name, role in (
    ("GATEWAY_BASE_URL", "api"),
    ("PRODUCT_OPS_BASE_URL", "productOps"),
    ("MEDIA_AVATAR_BASE_URL", "mediaAvatar"),
    ("MEDIA_IMAGE_BASE_URL", "mediaImage"),
    ("MEDIA_VIDEO_BASE_URL", "mediaVideo"),
    ("MEDIA_UPLOAD_BASE_URL", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(bases[role]))}")
for name, role in (
    ("QWQ_PUBLIC_API_HOST", "api"),
    ("QWQ_PUBLIC_WEB_HOST", "publicWeb"),
    ("QWQ_PUBLIC_RTC_HOST", "rtc"),
    ("QWQ_PUBLIC_OPS_HOST", "productOps"),
    ("QWQ_PUBLIC_CDN_HOST", "mediaImage"),
    ("QWQ_PUBLIC_UPLOAD_HOST", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(urlsplit(str(bases[role])).hostname))}")
PY
)"
PUBLIC_HOSTS=(
  "$QWQ_PUBLIC_API_HOST"
  "$QWQ_PUBLIC_WEB_HOST"
  "$QWQ_PUBLIC_OPS_HOST"
  "$QWQ_PUBLIC_CDN_HOST"
  "$QWQ_PUBLIC_UPLOAD_HOST"
)
LOCAL_GAMMA_TAGS_DIR="${LOCAL_GAMMA_TAGS_DIR:-$ROOT/quwoquan_data/control_plane/governance/taxonomy}"
LOCAL_GAMMA_TAG_DB="${LOCAL_GAMMA_TAG_DB:-quwoquan_tag}"
# 2G onebox 在 gray/prod 切换窗口会短时双栈并存；显式压低 Mongo cache，避免数据面被 OOM kill。
LOCAL_GAMMA_MONGO_CACHE_SIZE_GB="${LOCAL_GAMMA_MONGO_CACHE_SIZE_GB:-0.25}"
# daocloud 镜像代理在部分网络下会 EOF；默认直连 Docker Hub，可通过环境变量覆盖。
DOCKER_LIBRARY_PREFIX="${LOCAL_GAMMA_DOCKER_LIBRARY_PREFIX:-docker.io/library}"
HOST_READY_TIMEOUT_SECONDS="${LOCAL_GAMMA_HOST_READY_TIMEOUT_SECONDS:-360}"
FORCE_CLEAN_RECREATE="${LOCAL_GAMMA_FORCE_CLEAN_RECREATE:-0}"
PRESERVE_POSTGRES_VOLUME="${LOCAL_GAMMA_PRESERVE_POSTGRES_VOLUME:-0}"
LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/rendered"
LOCAL_GAMMA_CACHE_ROOT="${QWQ_OUTPUT_ROOT}/env/${QWQ_LOCAL_RELEASE_ENV}/local/${QWQ_LOCAL_RELEASE_TARGET}/cache"
LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/${QWQ_LOCAL_RELEASE_ENV}/local/${QWQ_LOCAL_RELEASE_TARGET}/process"
LOCAL_GAMMA_RUNTIME_LOG_ROOT="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
GAMMA_RUN_ROOT="${QWQ_RUN_ROOT}"
# 渲染配置是部署过程临时输入，真相源始终在 Ops/服务的 deploy 与 configs 目录。
LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/config-root"
LOCAL_GAMMA_MEDIA_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/media"
# Ops owns the immutable local-gamma route table. Runtime output never carries static routing config.
LOCAL_GAMMA_CADDYFILE="$ROOT/quwoquan_ops/environments/gamma/local/Caddyfile"
LOCAL_GAMMA_CADDY_DATA_VOLUME="${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}"
LOCAL_GAMMA_CADDY_CONFIG_VOLUME="${LOCAL_GAMMA_CADDY_CONFIG_VOLUME:-local-gamma-caddy-config}"
tls_exports="$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT/quwoquan_ops/cli/lib/public_domain_tls.py" paths \
    --target "$QWQ_LOCAL_RELEASE_TARGET" \
    --format shell \
    --allow-missing
)" || exit $?
eval "$tls_exports"
LOCAL_GAMMA_MODEL_CACHE_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/model"
LOCAL_GAMMA_PORTAL_ROOT="${LOCAL_GAMMA_PORTAL_ROOT:-${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/build/ops-portal}"
LOCAL_GAMMA_STACK_STATUS_REPORT="${LOCAL_GAMMA_PROCESS_ROOT}/stack_status.json"
STAGE="${STAGE:-$QWQ_LOCAL_RELEASE_ENV}"
LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-}"
CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-}"
LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-}"
case "$STAGE" in
  alpha|beta|gamma)
    if [[ "$STAGE" != "$QWQ_LOCAL_RELEASE_ENV" ]]; then
      echo "[local-release] GATE_BLOCK: stage does not match environment" >&2
      exit 2
    fi
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-$QWQ_LOCAL_RELEASE_ENV}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-$QWQ_LOCAL_RELEASE_ENV}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-local-${QWQ_LOCAL_RELEASE_ENV}}"
    # gamma-local 保持生产 Remote composition 与完整第一方拓扑；
    # 所有外部 Provider 由服务 Binding 选择 Port 对等本地替身，并由 stackctl 统一材料化。
    ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-assistant_p0_core}"
    ;;
  prod)
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-prod}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-prod}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-prod-onebox}"
    # prod 只消费 environments/prod 的真实 Provider Binding，缺凭据必须 fail-fast。
    ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-}"
    ;;
  *)
    echo "[local-release] FAIL: unsupported STAGE=$STAGE" >&2
    exit 2
    ;;
esac
LOCAL_GAMMA_LEGAL_STATIC_ROOT="${LOCAL_GAMMA_LEGAL_STATIC_ROOT:-$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir

print(legal_static_deployment_package_dir(sys.argv[1]) / "current" / "public")
PY
)}"
LOCAL_GAMMA_READY_INDEX_STREAM="${LOCAL_GAMMA_READY_INDEX_STREAM:-reliabletask:chat:avatar:ready:${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_GROUP="${LOCAL_GAMMA_READY_INDEX_GROUP:-chat.group_avatar_worker.${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_QUEUE="${LOCAL_GAMMA_READY_INDEX_QUEUE:-reliabletask.chat.avatar}"
export \
  STAGE \
  LOCAL_GAMMA_APP_ENV \
  CONFIG_SOURCE_ENV \
  ASSISTANT_SCENARIO_SEED_REFS \
  LOCAL_GAMMA_READY_INDEX_STREAM \
  LOCAL_GAMMA_READY_INDEX_GROUP \
  LOCAL_GAMMA_READY_INDEX_QUEUE \
  LOCAL_GAMMA_CADDY_DATA_VOLUME \
  LOCAL_GAMMA_CADDY_CONFIG_VOLUME \
  LOCAL_GAMMA_COMPOSE_PROJECT_NAME \
  QWQ_PUBLIC_TLS_CERT_FILE \
  QWQ_PUBLIC_TLS_KEY_FILE \
  QWQ_PUBLIC_API_HOST \
  QWQ_PUBLIC_WEB_HOST \
  QWQ_PUBLIC_RTC_HOST \
  QWQ_PUBLIC_OPS_HOST \
  QWQ_PUBLIC_CDN_HOST \
  QWQ_PUBLIC_UPLOAD_HOST \
  MEDIA_AVATAR_BASE_URL \
  MEDIA_IMAGE_BASE_URL \
  MEDIA_VIDEO_BASE_URL \
  MEDIA_UPLOAD_BASE_URL \
  LOCAL_GAMMA_CONFIG_ROOT \
  LOCAL_GAMMA_MEDIA_ROOT \
  LOCAL_GAMMA_MODEL_CACHE_ROOT \
  LOCAL_GAMMA_PORTAL_ROOT \
  GAMMA_RUN_ROOT \
  LOCAL_GAMMA_LEGAL_STATIC_ROOT
export QWQ_LOCAL_RELEASE_ENV QWQ_LOCAL_RELEASE_TARGET

library_image() {
  local image="$1"
  printf '%s/%s' "${DOCKER_LIBRARY_PREFIX%/}" "$image"
}

export LOCAL_GAMMA_POSTGRES_IMAGE="${LOCAL_GAMMA_POSTGRES_IMAGE:-$(library_image postgres:16-alpine)}"
export LOCAL_GAMMA_MONGO_IMAGE="${LOCAL_GAMMA_MONGO_IMAGE:-$(library_image mongo:7-jammy)}"
export LOCAL_GAMMA_REDIS_IMAGE="${LOCAL_GAMMA_REDIS_IMAGE:-$(library_image redis:7.2-alpine)}"
export LOCAL_GAMMA_GO_BOOKWORM_IMAGE="${LOCAL_GAMMA_GO_BOOKWORM_IMAGE:-$(library_image golang:1.24-bookworm)}"
export LOCAL_GAMMA_CADDY_IMAGE="${LOCAL_GAMMA_CADDY_IMAGE:-$(library_image caddy:2.8.4-alpine)}"
export LOCAL_GAMMA_MINIO_IMAGE="${LOCAL_GAMMA_MINIO_IMAGE:-minio/minio:RELEASE.2025-04-22T22-12-26Z}"
export LOCAL_GAMMA_MINIO_MC_IMAGE="${LOCAL_GAMMA_MINIO_MC_IMAGE:-minio/mc:RELEASE.2025-03-12T17-29-24Z}"
# ES 镜像来自 elastic 官方 registry（非 docker.io/library），不经 library_image 前缀。
export LOCAL_GAMMA_ELASTICSEARCH_IMAGE="${LOCAL_GAMMA_ELASTICSEARCH_IMAGE:-docker.elastic.co/elasticsearch/elasticsearch:8.13.4}"
case "$(uname -m)" in
  arm64|aarch64)
    # Apple Silicon 的 Colima/VZ 会向 bundled JDK 报告 guest 无法执行的
    # SVE；ES CLI bootstrap 与运行时都必须在 Elasticsearch 启动前禁用它。
    export LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS:--XX:UseSVE=0}"
    export LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS:--XX:UseSVE=0 -Xms512m -Xmx512m}"
    ;;
  *)
    export LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS:-}"
    export LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS:--Xms512m -Xmx512m}"
    ;;
esac
export LOCAL_GAMMA_GO_BASE_IMAGE="${LOCAL_GAMMA_GO_BASE_IMAGE:?LOCAL_GAMMA_GO_BASE_IMAGE is required}"
export LOCAL_GAMMA_ALPINE_BASE_IMAGE="${LOCAL_GAMMA_ALPINE_BASE_IMAGE:?LOCAL_GAMMA_ALPINE_BASE_IMAGE is required}"
export LOCAL_GAMMA_PYTHON_BASE_IMAGE="${LOCAL_GAMMA_PYTHON_BASE_IMAGE:-$(library_image python:3.11-slim)}"

validate_local_gamma_image_composition() {
  local expected_version="${LOCAL_GAMMA_IMAGE_VERSION:-}"
  local service=""
  local service_key=""
  local image_key=""
  local image_ref=""
  local -a composition_args=("$expected_version")
  while IFS= read -r service; do
    service_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    image_key="LOCAL_GAMMA_${service_key}_IMAGE"
    image_ref="${!image_key:-}"
    if [[ -z "$image_ref" ]]; then
      echo "[local-release] GATE_BLOCK: ${image_key} is required from canonical image composition" >&2
      return 2
    fi
    export "$image_key"
    composition_args+=("$service" "$image_ref")
  done < <(first_party_image_owners)
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "${composition_args[@]}" <<'PY'
import sys

from quwoquan_ops.cli.lib.immutable_image_composition import immutable_image_digest

expected = sys.argv[1]
bindings = dict(zip(sys.argv[2::2], sys.argv[3::2], strict=True))
actual = immutable_image_digest(bindings)
if expected != actual:
    raise SystemExit(
        "[local-release] GATE_BLOCK: image composition version does not match exact refs"
    )
PY
  IMAGE_VERSION="$expected_version"
  export LOCAL_GAMMA_IMAGE_VERSION IMAGE_VERSION
}

skip_build=0
skip_up=0
build_only=0
build_services_csv=""
formal_release=0
formal_release_teardown=0
print_env=0
down=0
tunnel_pid_file="${LOCAL_GAMMA_PROCESS_ROOT}/colima-tunnels.pids"
stack_report="${LOCAL_GAMMA_STACK_STATUS_REPORT}"
gamma_proxy_ensure_attempts=0
compose_up_timed_out=0
compose_build_timed_out=0

# wait_local_gamma_host_ready() 会在 podman/manual 与 docker compose 两条路径共用。
# docker compose 分支会在后面重载成真实探测逻辑；这里提供默认 noop，
# 避免 podman/manual 路径命中“command not found”。
ensure_docker_gamma_proxy_started() {
  return 0
}

local_gamma_has_existing_stack() {
  export_service_compose_environment
  if docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" ps -q 2>/dev/null | awk 'NF {found=1} END {exit found ? 0 : 1}'; then
    return 0
  fi
  if command -v podman >/dev/null 2>&1 && \
    podman ps -a --format '{{.Names}}' 2>/dev/null | awk '/^quwoquan_service_(gamma-proxy|assistant-service|user-service|chat-service|content-service|product-ops-service|platform-ops-service|tag-service|search-service|entity-service|circle-service|integration-service|notification-service|recommendation-service|elasticsearch|redis|mongodb|postgres)_1$/ {found=1} END {exit found ? 0 : 1}'; then
    return 0
  fi
  return 1
}

stop_colima_tunnels() {
  if [[ ! -f "$tunnel_pid_file" ]]; then
    return 0
  fi
  while IFS= read -r pid; do
    if [[ -n "$pid" ]]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done < "$tunnel_pid_file"
  rm -f "$tunnel_pid_file"
}

LOCAL_GAMMA_MANAGED_CONTAINER_BASE_NAMES=(
  gamma-proxy
  assistant-service
  user-service
  chat-service
  content-service
  product-ops-service
  platform-ops-service
  tag-service
  search-service
  entity-service
  circle-service
  integration-service
  notification-service
  mongo-init
  recommendation-service
  elasticsearch
  redis
  mongodb
  postgres
)

cleanup_stale_named_gamma_containers() {
  local base_name=""
  local container_name=""
  local status=""
  for base_name in "${LOCAL_GAMMA_MANAGED_CONTAINER_BASE_NAMES[@]}"; do
    for container_name in "quwoquan_service_${base_name}_1" "quwoquan_service-${base_name}-1"; do
      status="$(docker inspect --format '{{.State.Status}}' "$container_name" 2>/dev/null || true)"
      if [[ -z "$status" ]]; then
        continue
      fi
      if [[ "$status" == "running" || "$status" == "restarting" || "$status" == "paused" ]]; then
        echo "[local-gamma] FAIL: unmanaged active container blocks canonical compose ownership: ${container_name} status=${status}" >&2
        return 1
      fi
      echo "[local-gamma] removing stale non-running container: ${container_name} status=${status}"
      docker rm "$container_name" >/dev/null
    done
  done
}

cleanup_existing_gamma_runtime() {
  local base_name=""
  local container_name=""
  local image_name=""
  for base_name in "${LOCAL_GAMMA_MANAGED_CONTAINER_BASE_NAMES[@]}"; do
    for container_name in "quwoquan_service_${base_name}_1" "quwoquan_service-${base_name}-1"; do
      docker rm -f "$container_name" >/dev/null 2>&1 || true
      if command -v podman >/dev/null 2>&1; then
        podman rm -f "$container_name" >/dev/null 2>&1 || true
      fi
    done
  done
  if command -v podman >/dev/null 2>&1; then
    podman pod rm -f quwoquan_service >/dev/null 2>&1 || true
    podman pod rm -f quwoquan_service_default >/dev/null 2>&1 || true
    if [[ "${skip_build:-0}" == "1" ]]; then
      return 0
    fi
    for image_name in \
      quwoquan_service_content-service \
      quwoquan_service_chat-service \
      quwoquan_service_user-service \
      quwoquan_service_assistant-service \
      quwoquan_service_product-ops-service \
      quwoquan_service_platform-ops-service \
      quwoquan_service_tag-service \
      quwoquan_service_search-service \
      quwoquan_service_entity-service \
      quwoquan_service_circle-service \
      quwoquan_service_integration-service \
      quwoquan_service_notification-service \
      quwoquan_service_recommendation-service \
      quwoquan_service_rtc-service; do
      podman rmi -f "$image_name" >/dev/null 2>&1 || true
      podman rmi -f "localhost/${image_name}:latest" >/dev/null 2>&1 || true
    done
  fi
}

host_port_open() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = sys.argv[1]
try:
    with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
        pass
except OSError:
    raise SystemExit(1)
raise SystemExit(0)
PY
}

start_colima_tunnels_if_needed() {
  command -v colima >/dev/null 2>&1 || return 0
  command -v ssh >/dev/null 2>&1 || return 0
  [[ "$(docker context show 2>/dev/null || true)" == "colima" ]] || return 0

  local http_port="${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local product_ops_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local media_edge_port="${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  # user-service 直连健康探针（wait_local_gamma_host_ready）使用 user_port，必须同步开隧道，
  # 否则 colima 下 host 无法直达 user-service 发布端口，host 就绪探测会卡死。
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local ssh_config="${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/runtime/colima-ssh-config"
  mkdir -p \
    "${LOCAL_GAMMA_PROCESS_ROOT}" \
    "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}" \
    "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" \
    "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}" \
    "$(dirname "$ssh_config")"
  stop_colima_tunnels
  colima ssh-config > "$ssh_config"
  : > "$tunnel_pid_file"
  for port in "$http_port" "$product_ops_port" "$media_edge_port" "$user_port"; do
    if host_port_open "$port"; then
      continue
    fi
    nohup python3 "$ROOT/quwoquan_ops/cli/lib/runtime_log_process.py" \
      --log-file "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}/colima-tunnel-${port}/local/runtime.log" \
      --event "colima-tunnel-${port}" -- \
      ssh -F "$ssh_config" -N -L "127.0.0.1:${port}:127.0.0.1:${port}" colima \
      </dev/null >/dev/null 2>&1 &
    echo "$!" >> "$tunnel_pid_file"
  done
  sleep 2
}

verify_public_dns() {
  python3 - "${PUBLIC_HOSTS[@]}" <<'PY'
import socket
import sys

failed = []
for host in sys.argv[1:]:
    resolved = sorted({item[4][0] for item in socket.getaddrinfo(host, None)})
    if not any(address.startswith("127.") or address == "::1" for address in resolved):
        failed.append(f"{host} -> {', '.join(resolved)}")
if failed:
    print("[local-gamma] GATE_BLOCK: gamma public hosts do not resolve to loopback:", file=sys.stderr)
    for item in failed:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)
PY
}

usage() {
  cat <<'USAGE'
Usage: quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh [options]

Options:
  --skip-build   Do not build Docker images.
  --skip-up      Prepare artifacts only; do not docker compose up.
  --build-only   Build the requested service images without starting Compose.
  --build-services <csv>
                 Comma-separated service names; valid only with --build-only.
  --formal-release
                 Reuse exact prebuilt candidate images and preserve the running data plane.
  --formal-release-teardown
                 Stop only the candidate-scoped Compose project; never repair or wipe.
  --print-env    Print Flutter dart-defines for the local gamma mirror.
  --down         Stop the local gamma mirror.
  --help         Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) skip_build=1; shift ;;
    --skip-up) skip_up=1; shift ;;
    --build-only) build_only=1; shift ;;
    --build-services)
      [[ $# -ge 2 ]] || {
        echo "--build-services requires a comma-separated service list" >&2
        exit 2
      }
      build_services_csv="$2"
      shift 2
      ;;
    --formal-release) formal_release=1; shift ;;
    --formal-release-teardown) formal_release_teardown=1; shift ;;
    --print-env) print_env=1; shift ;;
    --down) down=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$formal_release_teardown" == "1" && "$down" != "1" ]]; then
  echo "[local-release] GATE_BLOCK: --formal-release-teardown requires --down" >&2
  exit 2
fi

if [[ "$build_only" == "1" && "$skip_build" == "1" ]]; then
  echo "--build-only cannot be combined with --skip-build" >&2
  exit 2
fi
if [[ "$build_only" == "1" && "$skip_up" == "1" ]]; then
  echo "--build-only cannot be combined with --skip-up" >&2
  exit 2
fi
if [[ -n "$build_services_csv" && "$build_only" != "1" ]]; then
  echo "--build-services is valid only with --build-only" >&2
  exit 2
fi
if [[ "$formal_release" == "1" ]]; then
  if [[ "$skip_build" != "1" || "$build_only" == "1" || "$down" == "1" ]]; then
    echo "[local-gamma] GATE_BLOCK: --formal-release requires --skip-build and cannot build/down" >&2
    exit 2
  fi
  FORCE_CLEAN_RECREATE=0
  PRESERVE_POSTGRES_VOLUME=1
fi
if [[ "$print_env" != "1" ]]; then
  validate_local_gamma_image_composition || exit $?
fi
restarted_from_previous=0
if [[ "$print_env" != "1" ]] && local_gamma_has_existing_stack; then
  restarted_from_previous=1
fi

prepare_config_root() {
  local out="${LOCAL_GAMMA_CONFIG_ROOT}"
  local package_root
  package_root="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import deployment_package_root

print(deployment_package_root(sys.argv[1]))
PY
)"
  local packaged_configuration_digest
  packaged_configuration_digest="$(
    PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" "$QWQ_LOCAL_RELEASE_TARGET" <<'PY'
import sys

from quwoquan_ops.cli.lib.immutable_configuration_composition import (
    packaged_configuration_digest,
)

print(packaged_configuration_digest(sys.argv[1], target=sys.argv[2]))
PY
  )" || return 1
  if [[ "$packaged_configuration_digest" != "$CONFIG_VERSION" ]]; then
    echo "[local-release] GATE_BLOCK: LOCAL_GAMMA_CONFIG_VERSION does not match the packaged runtime configuration" >&2
    return 1
  fi

  copy_service_package_config() {
    local service="$1"
    local package_dir="${package_root}/services/${service}"
    local config_file="${package_dir}/config/config.yaml"
    local provenance_file="${package_dir}/provenance.json"
    if [[ ! -f "$config_file" || ! -f "$provenance_file" ]]; then
      echo "[local-gamma] FAIL: missing autonomous service package for ${service}: ${package_dir}" >&2
      return 1
    fi
    local config_version
    config_version="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$service" "$CONFIG_SOURCE_ENV" "$config_file" "$provenance_file" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

service, environment, config_value, provenance_value = sys.argv[1:5]
config_path = Path(config_value)
provenance_path = Path(provenance_value)
provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
actual = "sha256:" + hashlib.sha256(config_path.read_bytes()).hexdigest()
if provenance.get("service") != service or provenance.get("environment") != environment:
    raise SystemExit(f"service package identity mismatch: {provenance_path}")
if (provenance.get("digests") or {}).get("config") != actual:
    raise SystemExit(f"service package config digest mismatch: {config_path}")
version = str(provenance.get("configVersion") or "")
if not re.fullmatch(r"sha256:[0-9a-f]{64}", version):
    raise SystemExit(f"invalid derived config version: {provenance_path}")
print(version)
PY
)" || return 1
    cp "$config_file" "$out/${service}.yaml"
    local service_env_key
    service_env_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    local version_var="LOCAL_GAMMA_${service_env_key}_CONFIG_VERSION"
    export "${version_var}=${config_version}"
  }

  rm -rf "$out"
  mkdir -p "$out/quwoquan_service/runtime/reliabletask/resources"
  local service
  while IFS= read -r service; do
    copy_service_package_config "$service"
  done < <(first_party_image_owners)

  local -a report_account_backfill_args=(
    --write-report-account-backfill
    "$QWQ_LOCAL_RELEASE_ENV"
    "$QWQ_LOCAL_RELEASE_TARGET"
    "$out/report-account-backfill.json"
    --empty
  )
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 \
    python3 -m quwoquan_ops.cli.lib.local_environment_auth \
      "${report_account_backfill_args[@]}" >/dev/null

  if [[ ! -f "$package_root/runtime-shared/module_catalog.yaml" || ! -f "$package_root/runtime-shared/retention_policy.yaml" ]]; then
    echo "[local-gamma] FAIL: missing runtime shared package: $package_root/runtime-shared" >&2
    return 1
  fi
  cp "$package_root/runtime-shared/module_catalog.yaml" "$out/quwoquan_service/runtime/reliabletask/resources/module_catalog.yaml"
  cp "$package_root/runtime-shared/retention_policy.yaml" "$out/quwoquan_service/runtime/reliabletask/resources/retention_policy.yaml"
}

prepare_media_root() {
  local media="${LOCAL_GAMMA_MEDIA_ROOT}"
  mkdir -p \
    "$media/media/avatar/s" \
    "$media/media/image/s" \
    "$media/media/video/s"
  local forbidden_media=""
  forbidden_media="$(
    find "$media/media" -type f \
      \( -path '*fixture*' -o -path '*test_fixtures*' -o -path '*mock*' -o -path '*seed*' \) \
      -print -quit
  )"
  if [[ -n "$forbidden_media" ]]; then
    echo "[local-gamma] GATE_BLOCK: environment media root contains fixture/mock/seed business media: $forbidden_media" >&2
    echo "[local-release] run immutable release full-sync before exposing $QWQ_LOCAL_RELEASE_TARGET media" >&2
    return 2
  fi
  echo "[local-gamma] release media root ready; Data CLI ship apply --full-sync owns public slices: $media"
}

validate_caddyfile_source() {
  if [[ ! -f "$LOCAL_GAMMA_CADDYFILE" ]]; then
    echo "[local-gamma] FAIL: missing Ops-owned Caddyfile: $LOCAL_GAMMA_CADDYFILE" >&2
    return 1
  fi
}

print_defines() {
  if ! python3 - <<'PY' >/dev/null 2>&1; then
import sys
raise SystemExit(0 if sys.version_info >= (3, 7) else 1)
PY
    echo "[local-gamma] skip dart defines: python3 >= 3.7 required" >&2
    return 0
  fi

  python3 "$ROOT/quwoquan_app/scripts/env/print_app_env_dart_defines.py" \
    --env "$LOCAL_GAMMA_APP_ENV" \
    --target "$QWQ_LOCAL_RELEASE_TARGET"
}

run_docker_probe_with_timeout() {
  local probe_pid=""
  local deadline=""
  local timeout_seconds="${LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS:?LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS is required}"
  if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS must be a positive integer" >&2
    return 2
  fi

  docker info --format '{{.ServerVersion}} {{.Driver}}' >/dev/null 2>&1 &
  probe_pid="$!"
  LOCAL_GAMMA_ACTIVE_CHILD_PID="$probe_pid"
  deadline=$((SECONDS + timeout_seconds))
  while kill -0 "$probe_pid" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "[local-gamma] GATE_BLOCK: Docker daemon did not answer readiness probe within ${timeout_seconds}s" >&2
      kill "$probe_pid" >/dev/null 2>&1 || true
      wait "$probe_pid" >/dev/null 2>&1 || true
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 124
    fi
    sleep 1
  done
  if wait "$probe_pid"; then
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return 0
  else
    local probe_status=$?
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return "$probe_status"
  fi
}

preflight_docker_daemon() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[local-release] GATE_BLOCK: docker is required for $QWQ_LOCAL_RELEASE_TARGET" >&2
    return 1
  fi
  echo "[local-gamma] checking Docker daemon readiness before compose build"
  run_docker_probe_with_timeout
}

ensure_local_gamma_base_images() {
  [[ "${podman_compose:-0}" == "1" ]] || return 0
  local image=""
  local -a required_images=(
    "$LOCAL_GAMMA_GO_BOOKWORM_IMAGE"
    "$LOCAL_GAMMA_ALPINE_BASE_IMAGE"
    "$LOCAL_GAMMA_PYTHON_BASE_IMAGE"
    "$LOCAL_GAMMA_POSTGRES_IMAGE"
    "$LOCAL_GAMMA_MONGO_IMAGE"
    "$LOCAL_GAMMA_REDIS_IMAGE"
    "$LOCAL_GAMMA_CADDY_IMAGE"
    "$LOCAL_GAMMA_ELASTICSEARCH_IMAGE"
  )
  for image in "${required_images[@]}"; do
    [[ -n "$image" ]] || continue
    if podman image exists "$image" >/dev/null 2>&1; then
      continue
    fi
    echo "[local-gamma] pulling missing base image: $image"
    podman pull --arch amd64 "$image" || podman pull "$image" || {
      echo "[local-gamma] FAIL: unable to pull required base image: $image" >&2
      return 1
    }
  done
}

expected_local_gamma_built_image_ref() {
  case "$1" in
    api-edge) printf '%s\n' "$LOCAL_GAMMA_API_EDGE_IMAGE" ;;
    recommendation-service) printf '%s\n' "$LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE" ;;
    content-service) printf '%s\n' "$LOCAL_GAMMA_CONTENT_SERVICE_IMAGE" ;;
    chat-service) printf '%s\n' "$LOCAL_GAMMA_CHAT_SERVICE_IMAGE" ;;
    user-service) printf '%s\n' "$LOCAL_GAMMA_USER_SERVICE_IMAGE" ;;
    assistant-service) printf '%s\n' "$LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE" ;;
    product-ops-service) printf '%s\n' "$LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE" ;;
    platform-ops-service) printf '%s\n' "$LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE" ;;
    tag-service) printf '%s\n' "$LOCAL_GAMMA_TAG_SERVICE_IMAGE" ;;
    search-service) printf '%s\n' "$LOCAL_GAMMA_SEARCH_SERVICE_IMAGE" ;;
    entity-service) printf '%s\n' "$LOCAL_GAMMA_ENTITY_SERVICE_IMAGE" ;;
    circle-service) printf '%s\n' "$LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE" ;;
    integration-service) printf '%s\n' "$LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE" ;;
    notification-service) printf '%s\n' "$LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE" ;;
    realtime-gateway) printf '%s\n' "$LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE" ;;
    rtc-service) printf '%s\n' "$LOCAL_GAMMA_RTC_SERVICE_IMAGE" ;;
    *) return 1 ;;
  esac
}

validate_local_gamma_built_images() {
  local service=""
  local image_ref=""
  for service in "${compose_build_services[@]}"; do
    image_ref="$(expected_local_gamma_built_image_ref "$service" || true)"
    [[ -n "$image_ref" ]] || continue
    if [[ "${podman_compose:-0}" == "1" ]]; then
      if podman image exists "$image_ref" >/dev/null 2>&1; then
        continue
      fi
    elif docker image inspect "$image_ref" >/dev/null 2>&1; then
      continue
    fi
    echo "[local-gamma] GATE_BLOCK: packaged image is unavailable: $image_ref" >&2
    echo "[local-gamma] Repair: run stackctl up without --skip-build to build the package-bound image." >&2
    return 1
  done
  return 0
}

podman_build_log_has_nonzero_exit_codes() {
  python3 - "$1" <<'PY'
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
codes = [int(match.group(1)) for match in re.finditer(r"(?m)^exit code:\s*(\d+)\s*$", text)]
raise SystemExit(0 if any(code != 0 for code in codes) else 1)
PY
}

run_compose_build() {
  local build_log="${QWQ_RUN_ROOT}/attachments/docker-build.log"
  local build_status=0
  mkdir -p "$(dirname "$build_log")"
  : >"$build_log"
  if ! preflight_docker_daemon; then
    echo "[local-gamma] FAIL: Docker preflight did not complete; startup aborted." >&2
    return 1
  fi
  ensure_local_gamma_base_images
  echo "[local-gamma] building services: ${compose_build_services[*]}"
  run_compose_build_with_timeout "$build_log" || build_status=$?
  if [[ "$build_status" -eq 0 && "${podman_compose:-0}" == "1" ]]; then
    if podman_build_log_has_nonzero_exit_codes "$build_log"; then
      echo "[local-gamma] FAIL: podman-compose build reported non-zero inner exit codes." >&2
      build_status=1
    fi
  fi
  if [[ "$build_status" -eq 0 ]] && ! validate_local_gamma_built_images; then
    build_status=1
  fi
  if [[ "$build_status" -eq 0 ]]; then
    return 0
  fi
  if python3 - "$build_log" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").lower()
raise SystemExit(0 if "no space left on device" in text else 1)
PY
  then
    echo "[local-gamma] FAIL: image build exhausted Docker/Colima disk ('no space left on device')." >&2
    echo "[local-gamma] Reclaim local container storage and rerun:" >&2
    echo "[local-gamma]   docker system df" >&2
    echo "[local-gamma]   docker builder prune -af" >&2
    echo "[local-gamma]   docker image prune -af" >&2
    echo "[local-gamma]   docker volume prune -f" >&2
    echo "[local-gamma]   colima stop && colima start --disk 100" >&2
  fi
  echo "[local-gamma] FAIL: image build failed; startup aborted. Build log: $build_log" >&2
  return 1
}

run_compose_build_with_timeout() {
  local build_log="$1"
  local compose_pid=""
  local deadline=""
  local last_progress_seconds=""
  local last_log_size="0"
  local current_log_size="0"
  local timeout_seconds="${LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS:?LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS is required}"
  local no_progress_timeout_seconds="${LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS:?LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS is required}"
  # Each service build compiles a complete Go module. Limit local Compose
  # concurrency so a onebox cannot exhaust its container filesystem with
  # simultaneous /tmp/go-build directories.
  local compose_parallel_limit="${LOCAL_GAMMA_COMPOSE_BUILD_PARALLEL_LIMIT:-1}"
  if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS must be a positive integer" >&2
    return 2
  fi
  if ! [[ "$no_progress_timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS must be a positive integer" >&2
    return 2
  fi
  if ! [[ "$compose_parallel_limit" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_BUILD_PARALLEL_LIMIT must be a positive integer" >&2
    return 2
  fi

  env \
    COMPOSE_PARALLEL_LIMIT="$compose_parallel_limit" \
    "${compose_cmd[@]}" build "${compose_build_services[@]}" >"$build_log" 2>&1 &
  compose_pid="$!"
  LOCAL_GAMMA_ACTIVE_CHILD_PID="$compose_pid"
  deadline=$((SECONDS + timeout_seconds))
  last_progress_seconds="$SECONDS"
  while kill -0 "$compose_pid" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      compose_build_timed_out=1
      echo "[local-gamma] FAIL: compose build exceeded ${timeout_seconds}s; preserving build log for inspection" >&2
      kill "$compose_pid" >/dev/null 2>&1 || true
      wait "$compose_pid" >/dev/null 2>&1 || true
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 124
    fi
    current_log_size=$(wc -c <"$build_log")
    if [[ "$current_log_size" != "$last_log_size" ]]; then
      last_log_size="$current_log_size"
      last_progress_seconds="$SECONDS"
    elif (( SECONDS - last_progress_seconds >= no_progress_timeout_seconds )); then
      echo "[local-gamma] FAIL: compose build produced no log progress for ${no_progress_timeout_seconds}s; preserving build log for inspection" >&2
      kill "$compose_pid" >/dev/null 2>&1 || true
      wait "$compose_pid" >/dev/null 2>&1 || true
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 125
    fi
    sleep 1
  done
  if wait "$compose_pid"; then
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return 0
  else
    local compose_status=$?
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return "$compose_status"
  fi
}

prepare_down_compose_environment() {
  # `docker compose down` still interpolates every declared service.  Teardown
  # uses the already-validated exact image composition and only fills non-image
  # parse inputs that Compose requires without starting a process.
  local down_config_version="$CONFIG_VERSION"
  local service=""
  local service_key=""
  local version_key=""
  while IFS= read -r service; do
    service_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    version_key="LOCAL_GAMMA_${service_key}_CONFIG_VERSION"
    if [[ -z "${!version_key:-}" ]]; then
      printf -v "$version_key" '%s' "$down_config_version"
    fi
    export "$version_key"
  done < <(first_party_image_owners)
  : "${LOCAL_GAMMA_REC_POLICY_SOURCE:=down-not-used}"
  export \
    LOCAL_GAMMA_CONFIG_ROOT \
    LOCAL_GAMMA_REC_POLICY_SOURCE
  export_service_compose_environment
}

if [[ "$print_env" == "1" ]]; then
  # This is an introspection command. It must not render configuration, create
  # runtime output, touch Docker, or alter the currently running environment.
  print_defines
  exit 0
fi

if [[ "$down" == "1" ]]; then
  stop_colima_tunnels
  prepare_down_compose_environment
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" down
  if [[ "$formal_release_teardown" != "1" ]]; then
    cleanup_stale_named_gamma_containers
  fi
  rm -f "$stack_report"
  exit 0
fi

prepare_config_root
prepare_media_root
mkdir -p \
  "${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}" \
  "${LOCAL_GAMMA_PROCESS_ROOT}" \
  "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}" \
  "${LOCAL_GAMMA_CACHE_ROOT}" \
  "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" \
  "${GAMMA_RUN_ROOT}" \
  "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}" \
  "${LOCAL_GAMMA_PORTAL_ROOT}" \
  "${QWQ_OUTPUT_ROOT}/env/repo/local/control-plane/process/platform-ops-service"
validate_caddyfile_source

if [[ "$skip_up" == "1" ]]; then
  echo "[local-gamma] prepared artifacts only"
  echo "[local-release] configurationDigest=$CONFIG_VERSION imageTransportTag=$IMAGE_VERSION"
  exit 0
fi

podman_compose=0
export_service_compose_environment
if docker --version 2>/dev/null | grep -qi 'podman' && command -v podman-compose >/dev/null 2>&1; then
  podman_compose=1
  compose_cmd=(podman-compose "${COMPOSE_FILE_ARGS[@]}" --podman-build-args=--pull=never --podman-run-args=--pull=never)
  compose_up_args=(up -d --no-build)
else
  compose_cmd=(docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}")
  compose_up_args=(up -d --remove-orphans)
  if [[ "$skip_build" == "1" ]]; then
    compose_up_args+=(--no-build)
  fi
fi
if [[ "$formal_release" == "1" && "$podman_compose" == "1" ]]; then
  echo "[local-gamma] GATE_BLOCK: formal release forbids the destructive podman compatibility path" >&2
  exit 2
fi
if [[ "$formal_release" == "1" ]]; then
  compose_up_args=(up -d --no-build)
fi

prepare_local_gamma_mongosh() {
  local container_cli="$1"
  if command -v mongosh >/dev/null 2>&1; then
    return 0
  fi
  local wrapper_dir="${LOCAL_GAMMA_PROCESS_ROOT}/bin"
  mkdir -p "$wrapper_dir"
  cat > "${wrapper_dir}/mongosh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

container_cli="${LOCAL_GAMMA_CONTAINER_CLI:?LOCAL_GAMMA_CONTAINER_CLI is required}"
compose_project="${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:?LOCAL_GAMMA_COMPOSE_PROJECT_NAME is required}"
container_name=""
for candidate in "${compose_project}-mongodb-1" "${compose_project}_mongodb_1"; do
  if "$container_cli" inspect "$candidate" >/dev/null 2>&1; then
    container_name="$candidate"
    break
  fi
done
if [[ -z "$container_name" ]]; then
  echo "local-gamma mongosh wrapper cannot find the MongoDB container" >&2
  exit 1
fi

rewritten=()
for arg in "$@"; do
  case "$arg" in
    mongodb://127.0.0.1:*)
      rewritten+=("mongodb://127.0.0.1:27017/?directConnection=true")
      ;;
    *)
      rewritten+=("$arg")
      ;;
  esac
done
exec "$container_cli" exec -i "$container_name" mongosh "${rewritten[@]}"
SH
  chmod 0755 "${wrapper_dir}/mongosh"
  export LOCAL_GAMMA_CONTAINER_CLI="$container_cli"
  export PATH="${wrapper_dir}:${PATH}"
}

if [[ "$podman_compose" == "1" ]]; then
  prepare_local_gamma_mongosh podman
else
  prepare_local_gamma_mongosh docker
fi

compose_build_services=(
  api-edge
  recommendation-service
  content-service
  chat-service
  user-service
  assistant-service
  product-ops-service
  platform-ops-service
  tag-service
  search-service
  entity-service
  circle-service
  integration-service
  notification-service
)
if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
  filtered_build_services=()
  for service_name in "${compose_build_services[@]}"; do
    [[ "$service_name" == "product-ops-service" ]] || filtered_build_services+=("$service_name")
  done
  compose_build_services=("${filtered_build_services[@]}")
fi
if [[ "$WORKLOAD" == "content-release" ]]; then
  filtered_build_services=()
  for service_name in "${compose_build_services[@]}"; do
    [[ "$service_name" == "assistant-service" ]] || filtered_build_services+=("$service_name")
  done
  compose_build_services=("${filtered_build_services[@]}")
fi
if [[ ",${COMPOSE_PROFILES:-}," == *,edge-media,* ]]; then
  compose_build_services+=(realtime-gateway)
  compose_build_services+=(rtc-service)
fi

if [[ -n "$build_services_csv" ]]; then
  requested_build_services=()
  IFS=',' read -r -a requested_build_services <<< "$build_services_csv"
  selected_build_services=()
  selected_build_service_count=0
  for requested_service in "${requested_build_services[@]}"; do
    requested_service="$(printf '%s' "$requested_service" | tr -d '[:space:]')"
    [[ -n "$requested_service" ]] || continue
    service_allowed=0
    for available_service in "${compose_build_services[@]}"; do
      if [[ "$available_service" == "$requested_service" ]]; then
        service_allowed=1
        break
      fi
    done
    if [[ "$service_allowed" != "1" ]]; then
      echo "[local-gamma] FAIL: --build-services contains unavailable service '$requested_service' for workload=$WORKLOAD" >&2
      exit 2
    fi
    if [[ "$selected_build_service_count" -gt 0 ]]; then
      for selected_service in "${selected_build_services[@]}"; do
        if [[ "$selected_service" == "$requested_service" ]]; then
          echo "[local-gamma] FAIL: --build-services contains duplicate '$requested_service'" >&2
          exit 2
        fi
      done
    fi
    selected_build_services+=("$requested_service")
    selected_build_service_count=$((selected_build_service_count + 1))
  done
  if [[ "$selected_build_service_count" == "0" ]]; then
    echo "[local-gamma] FAIL: --build-services must contain at least one service" >&2
    exit 2
  fi
  compose_build_services=("${selected_build_services[@]}")
fi

if [[ "$FORCE_CLEAN_RECREATE" == "1" ]]; then
  echo "[local-gamma] forcing clean recreate of existing gamma containers"
  cleanup_existing_gamma_runtime
  if [[ "$podman_compose" != "1" ]]; then
    compose_up_args+=(--force-recreate)
  fi
fi

if [[ "$skip_build" == "0" ]]; then
  run_compose_build
elif ! validate_local_gamma_built_images; then
  exit 1
fi
if [[ "$build_only" == "1" ]]; then
  echo "[local-gamma] built services only: ${compose_build_services[*]}"
  exit 0
fi
export LOCAL_GAMMA_CONFIG_VERSION="$CONFIG_VERSION"
export LOCAL_GAMMA_IMAGE_VERSION="$IMAGE_VERSION"
export LOCAL_GAMMA_APP_ENV
export LOCAL_GAMMA_READY_INDEX_STREAM
export LOCAL_GAMMA_READY_INDEX_GROUP
export LOCAL_GAMMA_READY_INDEX_QUEUE
if [[ "$podman_compose" == "1" ]]; then
  echo "[local-gamma] startup mode: podman-manual"
  wait_healthy() {
    local name="$1"
    local status=""
    for _ in $(seq 1 60); do
      status="$(podman inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "healthy" || "$status" == "running" ]]; then
        return 0
      fi
      sleep 2
    done
    echo "[local-gamma] container did not become healthy: $name status=$status" >&2
    podman logs --tail 80 "$name" >&2 || true
    return 1
  }

  wait_running() {
    local name="$1"
    local status=""
    for _ in $(seq 1 60); do
      status="$(podman inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "running" ]]; then
        return 0
      fi
      sleep 2
    done
    echo "[local-gamma] container did not start: $name status=$status" >&2
    podman logs --tail 80 "$name" >&2 || true
    return 1
  }

  wait_exited_zero() {
    local name="$1"
    local status=""
    local exit_code=""
    for _ in $(seq 1 60); do
      status="$(podman inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      exit_code="$(podman inspect --format '{{.State.ExitCode}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "exited" && "$exit_code" == "0" ]]; then
        return 0
      fi
      sleep 2
    done
    echo "[local-gamma] one-shot container failed: $name status=$status exit=$exit_code" >&2
    podman logs --tail 80 "$name" >&2 || true
    return 1
  }

  network_name="quwoquan_service_default"
  for container_name in \
    quwoquan_service_gamma-proxy_1 \
    quwoquan_service_assistant-service_1 \
    quwoquan_service_user-service_1 \
    quwoquan_service_chat-service_1 \
    quwoquan_service_content-service_1 \
    quwoquan_service_product-ops-service_1 \
    quwoquan_service_platform-ops-service_1 \
    quwoquan_service_tag-service_1 \
    quwoquan_service_search-service_1 \
    quwoquan_service_entity-service_1 \
    quwoquan_service_circle-service_1 \
    quwoquan_service_integration-service_1 \
    quwoquan_service_notification-service_1 \
    quwoquan_service_mongo-init_1 \
    quwoquan_service_recommendation-service_1 \
    quwoquan_service_elasticsearch_1 \
    quwoquan_service_redis_1 \
    quwoquan_service_mongodb_1 \
    quwoquan_service_postgres_1; do
    podman rm -f "$container_name" >/dev/null 2>&1 || true
  done
  podman network exists "$network_name" || podman network create "$network_name" >/dev/null
  # Default cold-build path still recreates Postgres for deterministic startup.
  # Restart/rollout mode may preserve the volume to avoid unnecessary full DB bootstrap.
  if [[ "$PRESERVE_POSTGRES_VOLUME" != "1" ]]; then
    podman volume rm -f quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || true
  fi
  podman volume inspect quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-postgres >/dev/null
  podman volume inspect quwoquan_service_local-gamma-mongo >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-mongo >/dev/null
  podman volume inspect quwoquan_service_local-gamma-redis >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-redis >/dev/null
  podman volume inspect quwoquan_service_local-gamma-go-cache >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-go-cache >/dev/null
  podman volume inspect quwoquan_service_local-gamma-es >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-es >/dev/null

  podman run --pull=never --name quwoquan_service_postgres_1 -d \
    --net "$network_name" --network-alias postgres \
    -e POSTGRES_USER=quwoquan -e POSTGRES_PASSWORD=quwoquan -e POSTGRES_DB=quwoquan \
    -v quwoquan_service_local-gamma-postgres:/var/lib/postgresql/data \
    -p "${LOCAL_GAMMA_POSTGRES_PORT:-19400}:5432" \
    --healthcheck-command "pg_isready -U quwoquan" \
    --healthcheck-interval 5s --healthcheck-timeout 3s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_POSTGRES_IMAGE" >/dev/null

  podman run --pull=never --name quwoquan_service_mongodb_1 -d \
    --net "$network_name" --network-alias mongodb \
    -v quwoquan_service_local-gamma-mongo:/data/db \
    -p "${LOCAL_GAMMA_MONGO_PORT:-19410}:27017" \
    "$LOCAL_GAMMA_MONGO_IMAGE" \
    --replSet rs0 \
    --bind_ip_all \
    --wiredTigerCacheSizeGB "${LOCAL_GAMMA_MONGO_CACHE_SIZE_GB}" >/dev/null

  podman run --pull=never --name quwoquan_service_redis_1 -d \
    --net "$network_name" --network-alias redis \
    -v quwoquan_service_local-gamma-redis:/data \
    -p "${LOCAL_GAMMA_REDIS_PORT:-19420}:6379" \
    --healthcheck-command "redis-cli ping" \
    --healthcheck-interval 5s --healthcheck-timeout 3s --healthcheck-retries 20 \
    "$LOCAL_GAMMA_REDIS_IMAGE" redis-server --appendonly yes >/dev/null

  podman run --pull=never --name quwoquan_service_elasticsearch_1 -d \
    --net "$network_name" --network-alias elasticsearch \
    -e discovery.type=single-node \
    -e xpack.security.enabled=false \
    -e xpack.security.http.ssl.enabled=false \
    -e CLI_JAVA_OPTS="$LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS" \
    -e ES_JAVA_OPTS="$LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS" \
    -v quwoquan_service_local-gamma-es:/usr/share/elasticsearch/data \
    -p "${LOCAL_GAMMA_ES_PORT:-19430}:9200" \
    --healthcheck-command "curl -fsS 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=1s' || exit 1" \
    --healthcheck-interval 10s --healthcheck-timeout 5s --healthcheck-start-period 120s --healthcheck-retries 30 \
    "$LOCAL_GAMMA_ELASTICSEARCH_IMAGE" >/dev/null

  wait_healthy quwoquan_service_postgres_1
  wait_running quwoquan_service_mongodb_1
  sleep 5
  wait_healthy quwoquan_service_redis_1
  wait_healthy quwoquan_service_elasticsearch_1

  podman run --pull=never --rm --name quwoquan_service_mongo-init_1 \
    --net "$network_name" --network-alias mongo-init \
    "$LOCAL_GAMMA_MONGO_IMAGE" bash -lc "mongosh --host mongodb:27017 --quiet --eval '
      try {
        rs.status().ok
      } catch (e) {
        rs.initiate({_id: \"rs0\", members: [{_id: 0, host: \"mongodb:27017\"}]})
      }
    '" >/dev/null

  podman run --pull=never --name quwoquan_service_recommendation-service_1 -d \
    --net "$network_name" --network-alias recommendation-service --network-alias recommendation-service \
    -e SERVICE_NAME=recommendation-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PYTHONUNBUFFERED=1 \
    -e MODEL_CACHE_DIR=/app/cache \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${LOCAL_GAMMA_MODEL_CACHE_ROOT}:/app/cache" \
    -p "${LOCAL_GAMMA_REC_MODEL_PORT:-19240}:8000" \
    --healthcheck-command "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\" || exit 1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 5 \
    "$LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_recommendation-service_1

  if [[ "$PRODUCT_TELEMETRY_AVAILABLE" == "1" ]]; then
    podman run --pull=never --name quwoquan_service_product-ops-service_1 -d \
      --net "$network_name" --network-alias product-ops-service \
      -e SERVICE_NAME=product-ops-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
      -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
      -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PRODUCT_OPS_SERVICE_ADDR=:18086 \
      -e MONGO_URI=mongodb://mongodb:27017 \
      -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
      -e PRODUCT_OPS_REDIS_REC_ADDR=redis:6379 -e PRODUCT_OPS_REDIS_GENERAL_ADDR=redis:6379 \
      -e PRODUCT_OPS_ELASTICSEARCH_ENDPOINT="${PRODUCT_OPS_ELASTICSEARCH_ENDPOINT:-http://elasticsearch:9200}" \
      -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
      -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
      -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
      -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
      -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
      -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
      -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
      -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
      -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
      -p "${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}:18086" \
      --healthcheck-command "wget -qO- http://127.0.0.1:18086/healthz >/dev/null 2>&1" \
      --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
      "$LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE" >/dev/null
    wait_healthy quwoquan_service_product-ops-service_1
  else
    echo "[local-gamma] product telemetry unavailable; skipping product-ops without blocking App startup."
  fi

  podman run --pull=never --name quwoquan_service_platform-ops-service_1 -d \
    --net "$network_name" --network-alias platform-ops-service \
    -e SERVICE_NAME=platform-ops-service -e APP_ENV=gamma-integration \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PLATFORM_OPS_SERVICE_ADDR=:18088 \
    -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e REPO_ROOT=/app \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${QWQ_OUTPUT_ROOT}/env/repo/local/control-plane/process/platform-ops-service:/app/.qwq_output/env/repo/local/control-plane/process/platform-ops-service" \
    -p "${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-19260}:18088" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18088/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_platform-ops-service_1

  podman run --pull=never --name quwoquan_service_content-service_1 -d \
    --net "$network_name" --network-alias content-service \
    -e SERVICE_NAME=content-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e MONGO_URI=mongodb://mongodb:27017 \
    -e REPORT_DATABASE_URL='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e CONTENT_REDIS_REC_ADDR=redis:6379 -e CONTENT_REDIS_GENERAL_ADDR=redis:6379 -e CONTENT_REDIS_REALTIME_ADDR=redis:6379 \
    -e CONTENT_OSS_ENDPOINT \
    -e CONTENT_OSS_ACCESS_KEY_ID \
    -e CONTENT_OSS_ACCESS_KEY_SECRET \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -e REC_MODEL_SERVICE_ENABLED=true -e REC_MODEL_SERVICE_URL=http://recommendation-service:8000 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_CONTENT_PORT:-19220}:18080" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18080/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CONTENT_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_content-service_1

  podman run --pull=never --name quwoquan_service_chat-service_1 -d \
    --net "$network_name" --network-alias chat-service \
    -e SERVICE_NAME=chat-service -e MODULE_PACKAGE=chat-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e CHAT_SERVICE_ADDR=:18081 \
    -e MONGO_URI=mongodb://mongodb:27017 -e MONGO_DATABASE=quwoquan_chat \
    -e CHAT_REDIS_REALTIME_ADDR=redis:6379 -e CHAT_REDIS_GENERAL_ADDR=redis:6379 \
    -e CHAT_REDIS_RELIABLE_TASK_ADDR=redis:6379 \
    -e RELIABLE_TASK_READY_INDEX_ENABLED=true \
    -e RELIABLE_TASK_READY_INDEX_STREAM="$LOCAL_GAMMA_READY_INDEX_STREAM" \
    -e RELIABLE_TASK_READY_INDEX_GROUP="$LOCAL_GAMMA_READY_INDEX_GROUP" \
    -e RELIABLE_TASK_READY_INDEX_QUEUE="$LOCAL_GAMMA_READY_INDEX_QUEUE" \
    -e CHAT_GROUP_AVATAR_CDN_BASE_URL="$MEDIA_AVATAR_BASE_URL" \
    -e CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT=/var/lib/quwoquan/chat-media \
    -e RUNTIME_SYNC_PATCH_TTL_HOURS=720 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${LOCAL_GAMMA_MEDIA_ROOT}:/var/lib/quwoquan/chat-media" \
    -p "${LOCAL_GAMMA_CHAT_PORT:-19200}:18081" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18081/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CHAT_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_chat-service_1

  podman run --pull=never --name quwoquan_service_user-service_1 -d \
    --net "$network_name" --network-alias user-service \
    -e SERVICE_NAME=user-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e USER_SERVICE_ADDR=:18081 \
    -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_user \
    -e TAG_MONGO_URI=mongodb://mongodb:27017 -e TAG_MONGO_DATABASE=quwoquan_tag \
    -e REDIS_ADDR=redis:6379 \
    -e IDENTITY_ONE_TAP_FIXTURE_ENDPOINT \
    -e IDENTITY_ONE_TAP_FIXTURE_ACCESS_KEY_ID \
    -e IDENTITY_ONE_TAP_FIXTURE_ACCESS_KEY_SECRET \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_TOKEN_URL \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_USER_INFO_URL \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_TOKEN_URL \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_USER_INFO_URL \
    -e IDENTITY_SOCIAL_FIXTURE_QQ_USER_INFO_URL \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_APP_ID \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_APP_SECRET \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_APP_ID \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_APP_PRIVATE_KEY_PEM \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_PLATFORM_PUBLIC_KEY_PEM \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_MERCHANT_PID \
    -e IDENTITY_SOCIAL_FIXTURE_QQ_APP_ID \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${ROOT}/quwoquan_service/contracts/metadata/user:/contracts/metadata/user:ro" \
    -v "${ROOT}/quwoquan_service/services/user-service/internal/account/user_account/infrastructure/migration:/internal/infrastructure/migration:ro" \
    -p "${LOCAL_GAMMA_USER_PORT:-19210}:18081" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18081/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_USER_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_user-service_1

  podman run --pull=never --name quwoquan_service_integration-service_1 -d \
    --net "$network_name" --network-alias integration-service \
    -e SERVICE_NAME=integration-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e INTEGRATION_SERVICE_ADDR=:18086 \
    -e INTEGRATION_MONGO_URI=mongodb://mongodb:27017 -e INTEGRATION_MONGO_DATABASE=quwoquan_integration \
    -e INTEGRATION_PUSH_ENABLED=true \
    -e INTEGRATION_SMS_FIXTURE_ENDPOINT \
    -e INTEGRATION_SMS_FIXTURE_TOKEN \
    -e INTEGRATION_PUSH_FIXTURE_USER_SERVICE_BASE_URL \
    -e INTEGRATION_PUSH_FIXTURE_HMAC_KEY \
    -e INTEGRATION_LOCATION_FIXTURE_BASE_URL \
    -e INTEGRATION_LOCATION_FIXTURE_AK \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
    -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
    -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
    -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_INTEGRATION_PORT:-19310}:18086" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18086/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_integration-service_1

  podman run --pull=never --name quwoquan_service_notification-service_1 -d \
    --net "$network_name" --network-alias notification-service \
    -e SERVICE_NAME=notification-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e NOTIFICATION_SERVICE_ADDR=:18087 \
    -e 'NOTIFICATION_MONGO_URI=mongodb://mongodb:27017/?replicaSet=rs0' \
    -e NOTIFICATION_MONGO_DATABASE=quwoquan_notification \
    -e NOTIFICATION_INTEGRATION_BASE_URL=http://integration-service:18086 \
    -e NOTIFICATION_INTEGRATION_TIMEOUT_MS=1500 \
    -e NOTIFICATION_USER_BASE_URL=http://user-service:18081 \
    -e NOTIFICATION_REALTIME_BASE_URL=http://realtime-gateway:18090 \
    -e NOTIFICATION_CLAIM_PER_SECOND=100 -e NOTIFICATION_DISPATCH_PER_SECOND=100 -e NOTIFICATION_RETRY_PER_SECOND=20 \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
    -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
    -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
    -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}:18087" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18087/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_notification-service_1

  if [[ "$WORKLOAD" == "full" ]]; then
    podman run --pull=never --name quwoquan_service_assistant-service_1 -d \
      --net "$network_name" --network-alias assistant-service \
      -e SERVICE_NAME=assistant-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
      -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
      -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e ASSISTANT_SERVICE_ADDR=:18087 \
      -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_assistant \
      -e REDIS_GENERAL_ADDR=redis:6379 -e REDIS_REC_ADDR=redis:6379 \
      -e ASSISTANT_MODEL_FIXTURE_ENDPOINT \
      -e ASSISTANT_MODEL_API_KEY \
      -e ASSISTANT_PUBLIC_SEARCH_FIXTURE_URL \
      -e ASSISTANT_WEATHER_FIXTURE_GEOCODING_URL \
      -e ASSISTANT_WEATHER_FIXTURE_FORECAST_URL \
      -e ASSISTANT_FINANCE_FIXTURE_CHART_URL \
      -e ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-}" \
      -e ASSISTANT_NOTIFICATION_BASE_URL=http://notification-service:18087 \
      -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
      -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
      -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
      -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
      -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
      -p "${LOCAL_GAMMA_ASSISTANT_PORT:-19230}:18087" \
      --healthcheck-command "wget -qO- http://127.0.0.1:18087/healthz >/dev/null 2>&1" \
      --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
      "$LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE" >/dev/null
    wait_healthy quwoquan_service_assistant-service_1
  fi

  podman run --pull=never --name quwoquan_service_tag-service_1 -d \
    --net "$network_name" --network-alias tag-service \
    -e SERVICE_NAME=tag-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e TAG_SERVICE_ADDR=:18092 \
    -e TAG_MONGO_URI=mongodb://mongodb:27017 -e TAG_MONGO_DATABASE=quwoquan_tag \
    -e TAG_REDIS_GENERAL_ADDR=redis:6379 \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
    -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
    -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
    -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_TAG_PORT:-19270}:18092" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18092/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_TAG_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_tag-service_1

  podman run --pull=never --name quwoquan_service_search-service_1 -d \
    --net "$network_name" --network-alias search-service \
    -e SERVICE_NAME=search-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -e SEARCH_MONGO_URI=mongodb://mongodb:27017 -e SEARCH_MONGO_DATABASE=quwoquan_search \
    -e SEARCH_REDIS_GENERAL_MODE=standalone -e SEARCH_REDIS_GENERAL_ADDR=redis:6379 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_SEARCH_PORT:-19280}:18095" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18095/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_SEARCH_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_search-service_1

  podman run --pull=never --name quwoquan_service_entity-service_1 -d \
    --net "$network_name" --network-alias entity-service \
    -e SERVICE_NAME=entity-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e ENTITY_MONGO_URI=mongodb://mongodb:27017 -e ENTITY_MONGO_DATABASE=quwoquan_entity \
    -e ENTITY_REDIS_ADDR=redis:6379 \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_ENTITY_PORT:-19290}:18084" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18084/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_ENTITY_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_entity-service_1

  podman run --pull=never --name quwoquan_service_circle-service_1 -d \
    --net "$network_name" --network-alias circle-service \
    -e SERVICE_NAME=circle-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e CIRCLE_SERVICE_ADDR=:18082 \
    -e CIRCLE_MONGO_URI=mongodb://mongodb:27017 -e CIRCLE_MONGO_DATABASE=quwoquan_circle \
    -e CIRCLE_REDIS_ADDR=redis:6379 \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_CIRCLE_PORT:-19300}:18082" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18082/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_circle-service_1

  podman run --pull=never --name quwoquan_service_gamma-proxy_1 -d \
    --net "$network_name" --network-alias gamma-proxy \
    -e QWQ_PUBLIC_TLS_CERT_FILE=/etc/caddy/tls/fullchain.pem \
    -e QWQ_PUBLIC_TLS_KEY_FILE=/etc/caddy/tls/privkey.pem \
    -e QWQ_PUBLIC_API_HOST="$QWQ_PUBLIC_API_HOST" \
    -e QWQ_PUBLIC_WEB_HOST="$QWQ_PUBLIC_WEB_HOST" \
    -e QWQ_PUBLIC_RTC_HOST="$QWQ_PUBLIC_RTC_HOST" \
    -e QWQ_PUBLIC_OPS_HOST="$QWQ_PUBLIC_OPS_HOST" \
    -e QWQ_PUBLIC_CDN_HOST="$QWQ_PUBLIC_CDN_HOST" \
    -v "${LOCAL_GAMMA_CADDYFILE}:/etc/caddy/Caddyfile:ro" \
    -v "${QWQ_PUBLIC_TLS_CERT_FILE}:/etc/caddy/tls/fullchain.pem:ro" \
    -v "${QWQ_PUBLIC_TLS_KEY_FILE}:/etc/caddy/tls/privkey.pem:ro" \
    -v "${LOCAL_GAMMA_MEDIA_ROOT}:/srv/media:ro" \
    -v "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}:/srv/legal:ro" \
    -v "${LOCAL_GAMMA_CADDY_DATA_VOLUME}:/data" \
    -v "${LOCAL_GAMMA_CADDY_CONFIG_VOLUME}:/config" \
    -p "${LOCAL_GAMMA_HTTP_PORT:-19000}:${LOCAL_GAMMA_HTTP_PORT:-19000}" \
    -p "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}:${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}" \
    -p "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}:${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}" \
    -p "${LOCAL_GAMMA_ADMIN_PORT:-2019}:2019" \
    --healthcheck-command "wget -qO- https://${QWQ_PUBLIC_API_HOST}:${LOCAL_GAMMA_HTTP_PORT:-19000}/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 5s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CADDY_IMAGE" >/dev/null
  wait_healthy quwoquan_service_gamma-proxy_1
else
  echo "[local-gamma] startup mode: compose-up"
  if [[ "$formal_release" != "1" ]]; then
    # Explicit local-development startup may recreate and repair its disposable mirror.
    "${compose_cmd[@]}" down --remove-orphans >/dev/null 2>&1 || true
    cleanup_stale_named_gamma_containers
    if docker volume inspect quwoquan_service_local-gamma-caddy-data >/dev/null 2>&1; then
      docker run --rm \
        -v quwoquan_service_local-gamma-caddy-data:/data \
        --entrypoint sh \
        "$LOCAL_GAMMA_CADDY_IMAGE" \
        -c 'rm -f /data/caddy/locks/*.lock' >/dev/null
    fi
    if [[ "$PRESERVE_POSTGRES_VOLUME" != "1" ]]; then
      docker volume rm -f quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || true
    fi
  else
    echo "[local-gamma] formal release preserves images and data"
  fi
  ensure_docker_gamma_proxy_started() {
    local name=""
    local status=""
    local health=""
    local deadline=$((SECONDS + 15))
    while (( SECONDS < deadline )); do
      name="$(docker ps -aq \
        --filter "label=com.docker.compose.project=${LOCAL_GAMMA_COMPOSE_PROJECT_NAME}" \
        --filter "label=com.docker.compose.service=gamma-proxy" | head -n 1)"
      if [[ -z "$name" ]]; then
        sleep 1
        continue
      fi
      status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      if [[ -n "$status" ]]; then
        break
      fi
      sleep 1
    done
    if [[ -z "$status" ]]; then
      echo "[local-gamma] WARN: gamma-proxy container missing after compose up" >&2
      return 1
    fi
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
    if [[ "$status" == "running" ]]; then
      if [[ "$health" == "healthy" || "$health" == "running" || "$health" == "starting" ]]; then
        return 0
      fi
      echo "[local-gamma] WARN: gamma-proxy running but unhealthy (health=$health)" >&2
      return 1
    fi
    gamma_proxy_ensure_attempts=$((gamma_proxy_ensure_attempts + 1))
    echo "[local-gamma] gamma-proxy status=$status health=${health:-unknown}; starting explicitly (attempt ${gamma_proxy_ensure_attempts})" >&2
    if ! docker start "$name" >/dev/null 2>&1; then
      echo "[local-gamma] WARN: failed to start gamma-proxy explicitly" >&2
      docker ps -a --filter "name=$name" >&2 || true
      docker logs --tail 80 "$name" >&2 || true
      return 1
    fi
    for _ in $(seq 1 30); do
      status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "running" && ( "$health" == "healthy" || "$health" == "running" || "$health" == "starting" ) ]]; then
        return 0
      fi
      sleep 1
    done
    echo "[local-gamma] WARN: gamma-proxy explicit start did not report ready state (status=$status health=$health)" >&2
    docker logs --tail 80 "$name" >&2 || true
    return 1
  }
  retry_compose_up_after_created_only_failure() {
    local created_count=""
    local running_count=""
    local arg=""
    local has_no_build=0
    local -a retry_args=("${compose_up_args[@]}")
    created_count="$(docker ps -aq \
      --filter "label=com.docker.compose.project=${LOCAL_GAMMA_COMPOSE_PROJECT_NAME}" \
      --filter status=created | wc -l | tr -d '[:space:]')"
    running_count="$(docker ps -q \
      --filter "label=com.docker.compose.project=${LOCAL_GAMMA_COMPOSE_PROJECT_NAME}" \
      --filter status=running | wc -l | tr -d '[:space:]')"
    if [[ "${created_count:-0}" == "0" ]]; then
      return 1
    fi
    if [[ "$compose_up_timed_out" != "1" && "${running_count:-0}" != "0" ]]; then
      return 1
    fi
    echo "[local-gamma] compose left ${created_count} created containers; retrying once from the already-built images" >&2
    if ! "${compose_cmd[@]}" down --remove-orphans; then
      echo "[local-gamma] FAIL: failed to remove created-only compose runtime before retry" >&2
      return 1
    fi
    cleanup_stale_named_gamma_containers
    for arg in "${retry_args[@]}"; do
      if [[ "$arg" == "--no-build" ]]; then
        has_no_build=1
        break
      fi
    done
    if [[ "$has_no_build" != "1" ]]; then
      retry_args+=(--no-build)
    fi
    run_compose_up_with_timeout "${retry_args[@]}"
  }
  run_compose_up_with_timeout() {
    local compose_pid=""
    local deadline=""
    # ElasticSearch cold boots on the constrained local Gamma VM can exceed
    # eight minutes while rebuilding Painless lookup data.  The previous
    # timeout tore down a healthy-in-progress stack and retried with images
    # that may not exist locally, so no service ever reached its readiness phase.
    local timeout_seconds="${LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS:?LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS is required}"
    if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
      echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS must be a positive integer" >&2
      return 2
    fi

    compose_up_timed_out=0
    "${compose_cmd[@]}" "$@" &
    compose_pid="$!"
    LOCAL_GAMMA_ACTIVE_CHILD_PID="$compose_pid"
    deadline=$((SECONDS + timeout_seconds))
    while kill -0 "$compose_pid" >/dev/null 2>&1; do
      if (( SECONDS >= deadline )); then
        compose_up_timed_out=1
        echo "[local-gamma] FAIL: compose up exceeded ${timeout_seconds}s; preserving the partial runtime for inspection" >&2
        kill "$compose_pid" >/dev/null 2>&1 || true
        wait "$compose_pid" >/dev/null 2>&1 || true
        LOCAL_GAMMA_ACTIVE_CHILD_PID=""
        return 124
      fi
      sleep 1
    done
    if wait "$compose_pid"; then
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 0
    else
      local compose_status=$?
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return "$compose_status"
    fi
  }
  if ! run_compose_up_with_timeout "${compose_up_args[@]}"; then
    if [[ "$compose_up_timed_out" == "1" ]]; then
      echo "[local-gamma] FAIL: compose start exceeded its bounded timeout; run stackctl inspect before an explicit restart" >&2
      exit 1
    elif retry_compose_up_after_created_only_failure; then
      echo "[local-gamma] compose created-only retry recovered startup"
    else
      echo "[local-gamma] FAIL: compose up failed; runtime readiness cannot be inferred from partial containers" >&2
      exit 1
    fi
  fi
  ensure_docker_gamma_proxy_started
fi
start_colima_tunnels_if_needed
verify_public_dns

# docker compose 分支不会逐项 wait_healthy；在宣告就绪前用主机侧探测避免 T3/T4 撞到端口未监听。
gamma_canonical_video_range_mime_ready() {
  local host="$1"
  local port="$2"
  local probe=""
  local status=""
  local content_type=""
  probe="$(
    curl -fsS \
      -H "Range: bytes=0-1" \
      -o /dev/null \
      -w '%{http_code}|%{content_type}' \
      "https://${host}:${port}/media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4"
  )" || return 1
  status="${probe%%|*}"
  content_type="${probe#*|}"
  [[ "$status" == "206" && "$content_type" == video/* ]]
}

gamma_product_ops_ready() {
  if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
    return 0
  fi
  curl -fsS "${PRODUCT_OPS_BASE_URL%/}/healthz" >/dev/null 2>&1
}

gamma_platform_ops_ready() {
  # platform-ops belongs to the full operational control-plane. The
  # content-release slice deliberately has no operator OIDC material and its
  # acceptance scope does not include that service.
  if [[ "$WORKLOAD" == "content-release" ]]; then
    return 0
  fi
  curl -fsS "http://127.0.0.1:${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-19260}/healthz" >/dev/null 2>&1
}

wait_local_gamma_host_ready() {
  local gw="${GATEWAY_BASE_URL%/}"
  local gw_host="$QWQ_PUBLIC_API_HOST"
  local gw_port="${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local product_ops_host="$QWQ_PUBLIC_OPS_HOST"
  local product_ops_public_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local media_host="$QWQ_PUBLIC_CDN_HOST"
  local video_host="$QWQ_PUBLIC_CDN_HOST"
  local media_edge_port="${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  local po_port="${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}"
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local integration_port="${LOCAL_GAMMA_INTEGRATION_PORT:-19310}"
  local notification_port="${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}"
  local tag_port="${LOCAL_GAMMA_TAG_PORT:-19270}"
  local deadline=$(( $(date +%s) + HOST_READY_TIMEOUT_SECONDS ))
  local last_gamma_proxy_retry=0
  echo "[local-gamma] waiting for host probes (${HOST_READY_TIMEOUT_SECONDS}s): ${gw}/healthz + ${PRODUCT_OPS_BASE_URL%/}/healthz + media health + internal health"
  while (( $(date +%s) < deadline )); do
    if (( $(date +%s) - last_gamma_proxy_retry >= 15 )); then
      ensure_docker_gamma_proxy_started || true
      last_gamma_proxy_retry=$(date +%s)
    fi
    if curl -fsS "https://${gw_host}:${gw_port}/healthz" >/dev/null 2>&1 \
      && gamma_product_ops_ready \
      && curl -fsS "https://${media_host}:${media_edge_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "https://${video_host}:${media_edge_port}/healthz" >/dev/null 2>&1 \
      && { [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]] || curl -fsS "http://127.0.0.1:${po_port}/healthz" >/dev/null 2>&1; } \
      && gamma_platform_ops_ready \
      && curl -fsS "http://127.0.0.1:${user_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${integration_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${notification_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${tag_port}/healthz" >/dev/null 2>&1
    then
      return 0
    fi
    sleep 2
  done
  echo "[local-gamma] FAIL: host cannot reach required Remote service health probes within ${HOST_READY_TIMEOUT_SECONDS}s" >&2
  curl -fsS "https://${gw_host}:${gw_port}/healthz" >&2 || true
  gamma_product_ops_ready >&2 || true
  curl -fsS "https://${media_host}:${media_edge_port}/healthz" >&2 || true
  curl -fsS "https://${video_host}:${media_edge_port}/healthz" >&2 || true
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" ps >&2 || true
  curl -fsS "http://127.0.0.1:${integration_port}/healthz" >&2 || true
  curl -fsS "http://127.0.0.1:${notification_port}/healthz" >&2 || true
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" logs --tail 80 gamma-proxy product-ops-service platform-ops-service user-service integration-service notification-service >&2 || true
  return 1
}
ensure_gamma_filter_catalog_release() {
  echo "[local-gamma] activating canonical FilterCatalogRelease"
  PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
    --output-format json \
    filter-catalog --target "$QWQ_LOCAL_RELEASE_TARGET" --action stage-and-activate
}
wait_local_gamma_host_ready
ensure_gamma_filter_catalog_release





echo "[local-gamma] immutable release activation owns business data and search projections; no environment seed path is available"

PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$stack_report" "${QWQ_RELEASE_CANDIDATE_DIGEST:-}" "$CONFIG_VERSION" "$IMAGE_VERSION" "$STAGE" "$LOCAL_GAMMA_APP_ENV" "$CONFIG_SOURCE_ENV" "$GATEWAY_BASE_URL" "$PRODUCT_OPS_BASE_URL" "$MEDIA_IMAGE_BASE_URL" "$restarted_from_previous" "$WORKLOAD" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from quwoquan_ops.cli.lib.immutable_image_composition import (
    first_party_service_names,
    immutable_image_digest,
    local_release_image_environment_key,
)

(
    report_path,
    candidate_digest,
    configuration_digest,
    image_transport_tag,
    stage,
    runtime_env,
    config_env,
    gateway,
    product_ops,
    media,
    restarted,
    workload,
) = sys.argv[1:13]
image_refs = {
    service: os.environ[local_release_image_environment_key(service)]
    for service in first_party_service_names()
}
derived_image_version = immutable_image_digest(image_refs)
if derived_image_version != image_transport_tag:
    raise SystemExit(
        "[local-release] GATE_BLOCK: runtime receipt image composition drifted"
    )
payload = {
    "status": "passed",
    "workload": workload,
    "serviceMode": "single-stack",
    "restartedFromPrevious": restarted == "1",
    "stage": stage,
    "candidateDigest": candidate_digest or None,
    "configurationDigest": configuration_digest,
    "imageTransportTag": image_transport_tag,
    "imageComposition": {
        "imageVersion": derived_image_version,
        "images": {
            service: {"ref": ref}
            for service, ref in sorted(image_refs.items())
        },
    },
    "composeProject": os.environ["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"],
    "runtimeEnv": runtime_env,
    "configEnv": config_env,
    "gatewayBaseUrl": gateway,
    "productOpsBaseUrl": product_ops,
    "mediaEdgeBaseUrl": media,
    "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
path = Path(report_path)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[local-gamma] service mode: single-stack"
echo "[local-gamma] mirror started"
echo "[local-gamma] gateway: $GATEWAY_BASE_URL"
echo "[local-gamma] product-ops: $PRODUCT_OPS_BASE_URL"
echo "[local-gamma] media-image: $MEDIA_IMAGE_BASE_URL"
echo "[local-gamma] dart defines:"
print_defines
