#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
LOCAL_RUN_ACTION="up"
for arg in "$@"; do
  if [[ "$arg" == "--down" ]]; then LOCAL_RUN_ACTION="down"; fi
done
eval "$(python3 "$ROOT/quwoquan_ops/cli/lib/local_run.py" \
  --env gamma --target gamma-local --action "$LOCAL_RUN_ACTION" --output-root "$QWQ_OUTPUT_ROOT")"
export QWQ_OUTPUT_ROOT QWQ_DEPLOY_WORK_ROOT QWQ_OBSERVABILITY_RUN_ROOT QWQ_RUN_ROOT
COMPOSE_FILE="$ROOT/quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
LOCAL_GAMMA_COMPOSE_PROJECT_NAME="${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:-quwoquan_service}"
if [[ -z "${LOCAL_GAMMA_HTTP_PORT:-}" \
   || -z "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_PLATFORM_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-}" \
   || -z "${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-}" \
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
   || -z "${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-}" \
   || -z "${LOCAL_GAMMA_POSTGRES_PORT:-}" \
   || -z "${LOCAL_GAMMA_MONGO_PORT:-}" \
   || -z "${LOCAL_GAMMA_REDIS_PORT:-}" \
   || -z "${LOCAL_GAMMA_ES_PORT:-}" ]]; then
  eval "$(python3 "$ROOT/quwoquan_ops/cli/print_local_port_profile.py" --profile gamma-local --format shell-defaults)"
fi
# docker compose 只读取导出的环境变量；这里把 canonical local-gamma 端口全部导出，
# 避免直接运行脚本/Makefile 时回退到 compose 文件里的旧默认端口。
export \
  LOCAL_GAMMA_HTTP_PORT \
  LOCAL_GAMMA_PRODUCT_OPS_PORT \
  LOCAL_GAMMA_PLATFORM_OPS_PORT \
  LOCAL_GAMMA_MEDIA_EDGE_PORT \
  LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT \
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
CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-local-gamma-v1}"
IMAGE_VERSION="${LOCAL_GAMMA_IMAGE_VERSION:-0.0.1}"
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-https://gamma-api.quwoquan-env.test:${LOCAL_GAMMA_HTTP_PORT}}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-https://gamma-product-ops.quwoquan-env.test:${LOCAL_GAMMA_PRODUCT_OPS_PORT}}"
MEDIA_AVATAR_BASE_URL="${LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL:-https://gamma-avatar.quwoquan-env.test:${LOCAL_GAMMA_MEDIA_EDGE_PORT}}"
MEDIA_IMAGE_BASE_URL="${LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL:-${LOCAL_GAMMA_MEDIA_PUBLIC_BASE_URL:-${LOCAL_GAMMA_MEDIA_BASE_URL:-https://gamma-image.quwoquan-env.test:${LOCAL_GAMMA_MEDIA_EDGE_PORT}}}}"
MEDIA_VIDEO_BASE_URL="${LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL:-https://gamma-video.quwoquan-env.test:${LOCAL_GAMMA_MEDIA_EDGE_PORT}}"
MEDIA_UPLOAD_BASE_URL="${LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL:-https://gamma-upload.quwoquan-env.test:${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT}}"
MEDIA_BASE_URL="$MEDIA_IMAGE_BASE_URL"
PUBLIC_HOSTS=(
  gamma-api.quwoquan-env.test
  gamma-product-ops.quwoquan-env.test
  gamma-avatar.quwoquan-env.test
  gamma-image.quwoquan-env.test
  gamma-video.quwoquan-env.test
  gamma-upload.quwoquan-env.test
)
LOCAL_GAMMA_TAGS_DIR="${LOCAL_GAMMA_TAGS_DIR:-$ROOT/quwoquan_data/control_plane/governance/taxonomy}"
LOCAL_GAMMA_TAG_OBJECTS_FILE="${LOCAL_GAMMA_TAG_OBJECTS_FILE:-$ROOT/quwoquan_service/contracts/metadata/tag/test_fixtures/scenarios/tag_scenarios.json}"
LOCAL_GAMMA_TAG_DB="${LOCAL_GAMMA_TAG_DB:-quwoquan_tag}"
# 2G onebox 在 gray/prod 切换窗口会短时双栈并存；显式压低 Mongo cache，避免数据面被 OOM kill。
LOCAL_GAMMA_MONGO_CACHE_SIZE_GB="${LOCAL_GAMMA_MONGO_CACHE_SIZE_GB:-0.25}"
# daocloud 镜像代理在部分网络下会 EOF；默认直连 Docker Hub，可通过环境变量覆盖。
DOCKER_LIBRARY_PREFIX="${LOCAL_GAMMA_DOCKER_LIBRARY_PREFIX:-docker.io/library}"
HOST_READY_TIMEOUT_SECONDS="${LOCAL_GAMMA_HOST_READY_TIMEOUT_SECONDS:-360}"
FORCE_CLEAN_RECREATE="${LOCAL_GAMMA_FORCE_CLEAN_RECREATE:-0}"
PRESERVE_POSTGRES_VOLUME="${LOCAL_GAMMA_PRESERVE_POSTGRES_VOLUME:-0}"
LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/gamma-local/rendered"
LOCAL_GAMMA_CACHE_ROOT="${QWQ_OUTPUT_ROOT}/env/gamma/local/gamma-local/cache"
LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/gamma/local/gamma-local/process"
LOCAL_GAMMA_RUNTIME_LOG_ROOT="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
GAMMA_RUN_ROOT="${QWQ_RUN_ROOT}"
# 渲染配置是部署过程临时输入，真相源始终在 Ops/服务的 deploy 与 configs 目录。
LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/config-root"
LOCAL_GAMMA_MEDIA_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/media"
# Ops owns the immutable local-gamma route table. Runtime output never carries static routing config.
LOCAL_GAMMA_CADDYFILE="$ROOT/quwoquan_ops/environments/local-gamma/Caddyfile"
LOCAL_GAMMA_CADDY_DATA_VOLUME="${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}"
LOCAL_GAMMA_CADDY_CONFIG_VOLUME="${LOCAL_GAMMA_CADDY_CONFIG_VOLUME:-local-gamma-caddy-config}"
LOCAL_GAMMA_MODEL_CACHE_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/model"
LOCAL_GAMMA_STACK_STATUS_REPORT="${LOCAL_GAMMA_PROCESS_ROOT}/stack_status.json"
LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT="${LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT:-30s}"
STAGE="${STAGE:-gamma}"
LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-}"
CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-}"
LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-}"
case "$STAGE" in
  ""|gamma|pre)
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-gamma}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-gamma}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-local-gamma}"
    ENABLE_FIXTURE_SEEDS="${ENABLE_FIXTURE_SEEDS:-1}"
    ASSISTANT_MODEL_PROVIDER="${ASSISTANT_MODEL_PROVIDER:-deterministic}"
    ALLOW_DETERMINISTIC_BETA="${ALLOW_DETERMINISTIC_BETA:-1}"
    ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-assistant_p0_core}"
    ;;
  prod)
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-prod}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-prod}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-prod-onebox}"
    ENABLE_FIXTURE_SEEDS="${ENABLE_FIXTURE_SEEDS:-0}"
    # ECS prod onebox: deterministic assistant unless a real provider is injected.
    ASSISTANT_MODEL_PROVIDER="${ASSISTANT_MODEL_PROVIDER:-deterministic}"
    ALLOW_DETERMINISTIC_BETA="${ALLOW_DETERMINISTIC_BETA:-1}"
    ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-}"
    ;;
  *)
    echo "[local-gamma] FAIL: unsupported STAGE=$STAGE (expected pre|gamma|prod)" >&2
    exit 2
    ;;
esac
if [[ "${LOCAL_GAMMA_SKIP_FIXTURE_SEEDS:-0}" == "1" ]]; then
  ENABLE_FIXTURE_SEEDS=0
fi
LOCAL_GAMMA_LEGAL_STATIC_ROOT="${LOCAL_GAMMA_LEGAL_STATIC_ROOT:-${QWQ_OUTPUT_ROOT}/env/${CONFIG_SOURCE_ENV}/release/legal-static/current/public}"
LOCAL_GAMMA_READY_INDEX_STREAM="${LOCAL_GAMMA_READY_INDEX_STREAM:-reliabletask:chat:avatar:ready:${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_GROUP="${LOCAL_GAMMA_READY_INDEX_GROUP:-chat.group_avatar_worker.${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_QUEUE="${LOCAL_GAMMA_READY_INDEX_QUEUE:-reliabletask.chat.avatar}"
PREVIOUS_IMAGE_VERSION="${PREVIOUS_IMAGE_VERSION:-${PREV_IMAGE_VERSION:-}}"
export \
  STAGE \
  LOCAL_GAMMA_APP_ENV \
  CONFIG_SOURCE_ENV \
  ENABLE_FIXTURE_SEEDS \
  ASSISTANT_MODEL_PROVIDER \
  ALLOW_DETERMINISTIC_BETA \
  ASSISTANT_SCENARIO_SEED_REFS \
  LOCAL_GAMMA_READY_INDEX_STREAM \
  LOCAL_GAMMA_READY_INDEX_GROUP \
  LOCAL_GAMMA_READY_INDEX_QUEUE \
  LOCAL_GAMMA_CADDY_DATA_VOLUME \
  LOCAL_GAMMA_CADDY_CONFIG_VOLUME \
  LOCAL_GAMMA_CONFIG_ROOT \
  LOCAL_GAMMA_MEDIA_ROOT \
  LOCAL_GAMMA_MODEL_CACHE_ROOT \
  GAMMA_RUN_ROOT \
  LOCAL_GAMMA_LEGAL_STATIC_ROOT \
  PREVIOUS_IMAGE_VERSION

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
export LOCAL_GAMMA_GO_ALPINE_BASE_IMAGE="${LOCAL_GAMMA_GO_ALPINE_BASE_IMAGE:-$(library_image golang:1.24-bookworm)}"
export LOCAL_GAMMA_ALPINE_BASE_IMAGE="${LOCAL_GAMMA_ALPINE_BASE_IMAGE:-$(library_image alpine:3.19)}"
export LOCAL_GAMMA_PYTHON_BASE_IMAGE="${LOCAL_GAMMA_PYTHON_BASE_IMAGE:-$(library_image python:3.11-slim)}"

local_gamma_service_default_image_ref() {
  case "$1" in
    rec-model-service) echo "localhost/quwoquan_service_rec-model-service:latest" ;;
    content-service) echo "localhost/quwoquan_service_content-service:latest" ;;
    chat-service) echo "localhost/quwoquan_service_chat-service:latest" ;;
    user-service) echo "localhost/quwoquan_service_user-service:latest" ;;
    assistant-service) echo "localhost/quwoquan_service_assistant-service:latest" ;;
    product-ops-service) echo "localhost/quwoquan_service_product-ops-service:latest" ;;
    platform-ops-service) echo "localhost/quwoquan_service_platform-ops-service:latest" ;;
    tag-service) echo "localhost/quwoquan_service_tag-service:latest" ;;
    search-service) echo "localhost/quwoquan_service_search-service:latest" ;;
    entity-service) echo "localhost/quwoquan_service_entity-service:latest" ;;
    circle-service) echo "localhost/quwoquan_service_circle-service:latest" ;;
    integration-service) echo "localhost/quwoquan_service_integration-service:latest" ;;
    notification-service) echo "localhost/quwoquan_service_notification-service:latest" ;;
    rtc-service) echo "localhost/quwoquan_service_rtc-service:latest" ;;
    *) return 1 ;;
  esac
}

local_gamma_service_repository_name() {
  case "$1" in
    rec-model-service) echo "recommendation-service" ;;
    content-service|chat-service|user-service|assistant-service|product-ops-service|platform-ops-service|tag-service|search-service|entity-service|circle-service|integration-service|notification-service|rtc-service) echo "$1" ;;
    *) return 1 ;;
  esac
}

resolve_local_gamma_service_image_ref() {
  local service="$1"
  local default_ref=""
  default_ref="$(local_gamma_service_default_image_ref "$service")" || return 1
  local root="${LOCAL_GAMMA_IMAGE_REPOSITORY_ROOT:-}"
  local tag="${IMAGE_VERSION:-${LOCAL_GAMMA_IMAGE_VERSION:-}}"
  if [[ -n "$root" && -n "$tag" ]]; then
    printf '%s/%s:%s\n' \
      "${root%/}" \
      "$(local_gamma_service_repository_name "$service")" \
      "$tag"
    return 0
  fi
  printf '%s\n' "$default_ref"
}

export LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE="${LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref rec-model-service)}"
export LOCAL_GAMMA_CONTENT_SERVICE_IMAGE="${LOCAL_GAMMA_CONTENT_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref content-service)}"
export LOCAL_GAMMA_CHAT_SERVICE_IMAGE="${LOCAL_GAMMA_CHAT_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref chat-service)}"
export LOCAL_GAMMA_USER_SERVICE_IMAGE="${LOCAL_GAMMA_USER_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref user-service)}"
export LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE="${LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref assistant-service)}"
export LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE="${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref product-ops-service)}"
export LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE="${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref platform-ops-service)}"
export LOCAL_GAMMA_TAG_SERVICE_IMAGE="${LOCAL_GAMMA_TAG_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref tag-service)}"
export LOCAL_GAMMA_SEARCH_SERVICE_IMAGE="${LOCAL_GAMMA_SEARCH_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref search-service)}"
export LOCAL_GAMMA_ENTITY_SERVICE_IMAGE="${LOCAL_GAMMA_ENTITY_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref entity-service)}"
export LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE="${LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref circle-service)}"
export LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE="${LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref integration-service)}"
export LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE="${LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref notification-service)}"
export LOCAL_GAMMA_RTC_SERVICE_IMAGE="${LOCAL_GAMMA_RTC_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref rtc-service)}"

skip_build=0
skip_up=0
print_env=0
down=0
tunnel_pid_file="${LOCAL_GAMMA_PROCESS_ROOT}/colima-tunnels.pids"
stack_report="${LOCAL_GAMMA_STACK_STATUS_REPORT}"
gamma_proxy_ensure_attempts=0

# wait_local_gamma_host_ready() 会在 podman/manual 与 docker compose 两条路径共用。
# docker compose 分支会在后面重载成真实探测逻辑；这里提供默认 noop，
# 避免 podman/manual 路径命中“command not found”。
ensure_docker_gamma_proxy_started() {
  return 0
}

local_gamma_has_existing_stack() {
  if docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" ps -q 2>/dev/null | awk 'NF {found=1} END {exit found ? 0 : 1}'; then
    return 0
  fi
  if command -v podman >/dev/null 2>&1 && \
    podman ps -a --format '{{.Names}}' 2>/dev/null | awk '/^quwoquan_service_(gamma-proxy|assistant-service|user-service|chat-service|content-service|product-ops-service|platform-ops-service|tag-service|search-service|entity-service|circle-service|integration-service|notification-service|rec-model-service|elasticsearch|redis|mongodb|postgres)_1$/ {found=1} END {exit found ? 0 : 1}'; then
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
  object-storage-init
  object-storage
  mongo-init
  rec-model-service
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
      quwoquan_service_rec-model-service \
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
  local object_storage_edge_port="${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-19130}"
  # user-service 直连健康探针（wait_local_gamma_host_ready）使用 user_port，必须同步开隧道，
  # 否则 colima 下 host 无法直达 user-service 发布端口，host 就绪探测会卡死。
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local ssh_config="${LOCAL_GAMMA_PROCESS_ROOT}/colima-ssh-config"
  mkdir -p \
    "${LOCAL_GAMMA_PROCESS_ROOT}" \
    "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}" \
    "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" \
    "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}"
  stop_colima_tunnels
  colima ssh-config > "$ssh_config"
  : > "$tunnel_pid_file"
  for port in "$http_port" "$product_ops_port" "$media_edge_port" "$object_storage_edge_port" "$user_port"; do
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

admin_shell() {
  local script="$1"
  if [[ "$(id -u)" == "0" ]]; then
    bash -c "$script"
    return 0
  fi
  if sudo -n true >/dev/null 2>&1; then
    sudo bash -c "$script"
    return 0
  fi
  if [[ "${QWQ_GAMMA_LOCAL_ALLOW_ADMIN_PROMPT:-${QWQ_LOCAL_ALLOW_ADMIN_PROMPT:-0}}" == "1" ]] \
    && command -v osascript >/dev/null 2>&1; then
    local quoted
    quoted="$(python3 - "$script" <<'PY'
import sys

print(repr(sys.argv[1]))
PY
)"
    osascript -e "do shell script ${quoted} with administrator privileges"
    return 0
  fi
  echo "[local-gamma] GATE_BLOCK: gamma HTTPS public hosts require /etc/hosts management." >&2
  echo "[local-gamma] Run once with admin rights, or set QWQ_GAMMA_LOCAL_ALLOW_ADMIN_PROMPT=1 to allow the macOS password prompt." >&2
  return 1
}

flush_host_cache() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    dscacheutil -flushcache >/dev/null 2>&1 || true
    killall -HUP mDNSResponder >/dev/null 2>&1 || true
  fi
}

ensure_public_hosts_mapping() {
  local tmp_hosts
  tmp_hosts="$(mktemp "${TMPDIR:-/tmp}/quwoquan-gamma-hosts.XXXXXX")"
  python3 - "$tmp_hosts" "${PUBLIC_HOSTS[@]}" <<'PY'
import re
import sys
from pathlib import Path

out_path = Path(sys.argv[1])
hosts = sys.argv[2:]
hosts_path = Path("/etc/hosts")
begin = "# BEGIN quwoquan gamma local public plane"
end = "# END quwoquan gamma local public plane"
block = f"{begin}\n127.0.0.1 {' '.join(hosts)}\n::1 {' '.join(hosts)}\n{end}\n"

current = hosts_path.read_text(encoding="utf-8", errors="replace")
next_text = re.sub(
    rf"{re.escape(begin)}.*?{re.escape(end)}\n?",
    "",
    current,
    flags=re.S,
).rstrip() + "\n\n" + block
out_path.write_text(next_text, encoding="utf-8")
PY
  chmod 0644 "$tmp_hosts"

  local needs_update=0
  if ! cmp -s "$tmp_hosts" /etc/hosts; then
    needs_update=1
  fi
  if (( needs_update == 1 )); then
    if [[ "${QWQ_GAMMA_LOCAL_ALLOW_ADMIN_PROMPT:-0}" == "1" ]] && admin_shell "/bin/cp '$tmp_hosts' /etc/hosts"; then
      flush_host_cache
    else
      rm -f "$tmp_hosts"
      echo "[local-gamma] WARN: gamma public hosts are not mapped in /etc/hosts; host checks will use explicit --resolve where supported." >&2
      echo "[local-gamma] WARN: set QWQ_GAMMA_LOCAL_ALLOW_ADMIN_PROMPT=1 for one-time hosts repair, or LOCAL_GAMMA_STRICT_PUBLIC_HOSTS=1 to block." >&2
      if [[ "${LOCAL_GAMMA_STRICT_PUBLIC_HOSTS:-0}" == "1" ]]; then
        return 1
      fi
      return 0
    fi
  fi
  rm -f "$tmp_hosts"

  if ! python3 - "${PUBLIC_HOSTS[@]}" <<'PY'
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
  then
    if [[ "${LOCAL_GAMMA_STRICT_PUBLIC_HOSTS:-0}" == "1" ]]; then
      return 1
    fi
    echo "[local-gamma] WARN: continuing without public host loopback mapping; probes that cannot pass --resolve may fail." >&2
  fi
}

usage() {
  cat <<'USAGE'
Usage: quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh [options]

Options:
  --skip-build   Do not build Docker images.
  --skip-up      Prepare artifacts only; do not docker compose up.
  --print-env    Print Flutter dart-defines for the local gamma mirror.
  --down         Stop the local gamma mirror.
  --help         Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) skip_build=1; shift ;;
    --skip-up) skip_up=1; shift ;;
    --print-env) print_env=1; shift ;;
    --down) down=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

restarted_from_previous=0
if local_gamma_has_existing_stack; then
  restarted_from_previous=1
fi

prepare_config_root() {
  local out="${LOCAL_GAMMA_CONFIG_ROOT}"
  local package_root="${QWQ_OUTPUT_ROOT}/env/${CONFIG_SOURCE_ENV}/release"
  copy_service_package_config() {
    local package_service="$1"
    local runtime_service="$2"
    local package_dir="${package_root}/service/${package_service}"
    if [[ ! -f "$package_dir/default_config.yaml" || ! -f "$package_dir/config.yaml" ]]; then
      echo "[local-gamma] FAIL: missing environment package for ${package_service}: ${package_dir}" >&2
      return 1
    fi
    python3 - "$package_dir" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

package_dir = Path(sys.argv[1])
report_path = package_dir / "report.json"
try:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    files = report["provenance"]["files"]
except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid package provenance: {report_path}: {exc}")
for name, filename in {
    "defaultConfig": "default_config.yaml",
    "environmentConfig": "config.yaml",
}.items():
    actual = "sha256:" + hashlib.sha256((package_dir / filename).read_bytes()).hexdigest()
    if files.get(name) != actual:
        raise SystemExit(f"package digest mismatch: {package_dir / filename}")
PY
    cp "$package_dir/default_config.yaml" "$out/configs/${runtime_service}/default/config.yaml"
    cp "$package_dir/config.yaml" "$out/configs/${runtime_service}/${CONFIG_SOURCE_ENV}/config.yaml"
  }
  rm -rf "$out"
  mkdir -p \
    "$out/configs/content-service/default" \
    "$out/configs/content-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/content-service/configs/releases" \
    "$out/configs/chat-service/default" \
    "$out/configs/chat-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/chat-service/configs/releases" \
    "$out/configs/user-service/default" \
    "$out/configs/user-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/user-service/configs/releases" \
    "$out/configs/assistant-service/default" \
    "$out/configs/assistant-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/assistant-service/configs/releases" \
    "$out/quwoquan_ops/environments" \
    "$out/configs/product-ops-service/default" \
    "$out/configs/product-ops-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/product-ops-service/configs/releases" \
    "$out/configs/platform-ops-service/default" \
    "$out/configs/platform-ops-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/platform-ops-service/configs/releases" \
    "$out/configs/recommendation-service/default" \
    "$out/configs/recommendation-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/recommendation-service/configs/releases" \
    "$out/configs/tag-service/default" \
    "$out/configs/tag-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/tag-service/configs/releases" \
    "$out/configs/search-service/default" \
    "$out/configs/search-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/search-service/configs/releases" \
    "$out/configs/entity-service/default" \
    "$out/configs/entity-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/entity-service/configs/releases" \
    "$out/configs/circle-service/default" \
    "$out/configs/circle-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/circle-service/configs/releases" \
    "$out/configs/integration-service/default" \
    "$out/configs/integration-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/integration-service/configs/releases" \
    "$out/configs/notification-service/default" \
    "$out/configs/notification-service/${CONFIG_SOURCE_ENV}" \
    "$out/quwoquan_service/services/notification-service/configs/releases"
  copy_service_package_config content-service content-service
  copy_service_package_config chat-service chat-service
  copy_service_package_config user-service user-service
  copy_service_package_config assistant-service assistant-service
  copy_service_package_config product-ops-service product-ops-service
  copy_service_package_config platform-ops-service platform-ops-service
  copy_service_package_config rec-model-service recommendation-service
  copy_service_package_config tag-service tag-service
  copy_service_package_config search-service search-service
  copy_service_package_config entity-service entity-service
  copy_service_package_config circle-service circle-service
  copy_service_package_config integration-service integration-service
  copy_service_package_config notification-service notification-service
  if [[ ! -f "$package_root/runtime-shared/reliable_task_module_catalog.yaml" || ! -f "$package_root/runtime-shared/reliable_task_retention_policy.yaml" ]]; then
    echo "[local-gamma] FAIL: missing runtime shared package: $package_root/runtime-shared" >&2
    return 1
  fi
  cp "$package_root/runtime-shared/reliable_task_module_catalog.yaml" "$out/quwoquan_ops/environments/reliable_task_module_catalog.yaml"
  cp "$package_root/runtime-shared/reliable_task_retention_policy.yaml" "$out/quwoquan_ops/environments/reliable_task_retention_policy.yaml"
  cat > "$out/quwoquan_service/services/content-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18080"
mongo:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_content"
  collection: "posts"
redis:
  rec:
    mode: standalone
    addr: "redis:6379"
    db: 0
    tls: false
  general:
    mode: standalone
    addr: "redis:6379"
    db: 1
    tls: false
rec_model_service:
  enabled: true
  url: "http://recommendation-service:8000"
  timeout_ms: 100
YAML
  cat > "$out/quwoquan_service/services/chat-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18081"
mongodb:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_chat"
redis:
  realtime:
    mode: standalone
    addr: "redis:6379"
    tls: false
  general:
    mode: standalone
    addr: "redis:6379"
    tls: false
  reliable_task:
    mode: standalone
    addr: "redis:6379"
    tls: false
runtime:
  media:
    group_avatar_cdn_base_url: "${MEDIA_BASE_URL}"
    group_avatar_local_media_root: "/var/lib/quwoquan/chat-media"
  sync:
    patch_ttl_hours: 720
  reliable_task:
    ready_index:
      enabled: true
      stream: "${LOCAL_GAMMA_READY_INDEX_STREAM}"
      group: "${LOCAL_GAMMA_READY_INDEX_GROUP}"
      queue: "${LOCAL_GAMMA_READY_INDEX_QUEUE}"
  observability:
    runtime_media:
      group_avatar_recompute_duration_ms_p95: 500
      group_avatar_fallback_ratio: 0.05
      hint_to_pull_delay_ms_p95: 500
      patch_fanout_failure_ratio: 0.01
YAML
  cat > "$out/quwoquan_service/services/user-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18082"
postgres:
  dsn: "postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable"
  max_open_conns: 25
  max_idle_conns: 5
  conn_max_lifetime_minutes: 30
mongodb:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_user"
redis:
  general:
    mode: standalone
    addr: "redis:6379"
    db: 0
    tls: false
YAML
  cat > "$out/quwoquan_service/services/assistant-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18087"
mongodb:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_assistant"
redis:
  rec:
    mode: standalone
    addr: "redis:6379"
    db: 0
    tls: false
  general:
    mode: standalone
    addr: "redis:6379"
    db: 1
    tls: false
YAML
  cat > "$out/quwoquan_service/services/product-ops-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18086"
mongodb:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_product_ops"
postgres:
  dsn: "postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable"
redis:
  rec:
    mode: standalone
    addr: "redis:6379"
    db: 0
    tls: false
  general:
    mode: standalone
    addr: "redis:6379"
    db: 1
    tls: false
YAML
  cat > "$out/quwoquan_service/services/platform-ops-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  name: "platform-ops-service"
  http:
    addr: ":18088"
postgres:
  dsn: "postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable"
YAML
  cat > "$out/quwoquan_service/services/recommendation-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":8000"
YAML
  cat > "$out/quwoquan_service/services/tag-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18092"
mongo:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_tag"
YAML
  # search-service：gamma 下 CONFIG_VERSION 必填且 release 版本文件必须存在（缺失即启动失败）。
  # es.endpoints / mongo.uri 经 SEARCH_ES_ENDPOINTS / SEARCH_MONGO_URI 注入并在配置加载后覆盖，
  # 这里 es.enabled 固定 true（与 gamma 主链路一致），endpoints 留空交由 env 注入。
  cat > "$out/quwoquan_service/services/search-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18095"
es:
  enabled: true
  endpoints: []
  index: "quwoquan_objects"
  shards: 1
  replicas: 1
mongo:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_search"
YAML
  # entity-service：gamma 下 CONFIG_VERSION 必填且 release 版本文件必须存在（缺失即启动失败）。
  # mongo/ES endpoints 经 ENTITY_MONGO_* / SEARCH_ES_* 注入；这里固定 addr 与共享检索索引名。
  cat > "$out/quwoquan_service/services/entity-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18084"
mongo:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_entity"
es:
  enabled: true
  endpoints: []
  index: "quwoquan_objects"
  shards: 1
  replicas: 1
YAML
  # circle-service：启动时强校验 config.version == CONFIG_VERSION，故 release 版本文件必须声明同一版本。
  # mongo/redis/ES endpoints 经 CIRCLE_MONGO_* / CIRCLE_REDIS_* / SEARCH_ES_* 注入。
  cat > "$out/quwoquan_service/services/circle-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18082"
mongo:
  uri: "mongodb://mongodb:27017"
  database: "quwoquan_circle"
redis:
  general:
    mode: standalone
    addr: "redis:6379"
    db: 0
    tls: false
es:
  enabled: true
  endpoints: []
  index: "quwoquan_objects"
  shards: 1
  replicas: 1
YAML
  cat > "$out/quwoquan_service/services/integration-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18086"
YAML
  cat > "$out/quwoquan_service/services/notification-service/configs/releases/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":18087"
YAML
}

verify_canonical_video_materialization() {
  python3 "$ROOT/quwoquan_ops/cli/lib/local_gamma_media.py" \
    verify --target-root "$LOCAL_GAMMA_MEDIA_ROOT"
}

prepare_media_root() {
  local media="${LOCAL_GAMMA_MEDIA_ROOT}"
  local canonical_media_root="$ROOT/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
  local required_sample="$media/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
  local required_avatar="$media/media/avatar/s/archived-avatar/circle/fixture_circle_coffee_04/v1/avatar.png"
  local required_video="$media/media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
  local media_file_count=0
  if [[ -d "$media/media" ]]; then
    media_file_count="$(find "$media/media" -type f | wc -l | tr -d '[:space:]')"
    if [[ -f "$required_sample" && -f "$required_avatar" && -f "$required_video" && "$media_file_count" -ge 1000 ]]; then
      verify_canonical_video_materialization
      echo "[local-gamma] reuse pre-synced full shared media bundle: $media"
      return 0
    fi
    echo "[local-gamma] gamma media root is incomplete; rebuilding full shared media bundle: $media (files=$media_file_count)" >&2
    rm -rf "$media"
  fi
  if [[ "$ENABLE_FIXTURE_SEEDS" != "1" ]]; then
    echo "[local-gamma] FAIL: STAGE=${STAGE} requires an existing media root at ${media}/media" >&2
    return 1
  fi
  if [[ -d "$canonical_media_root" ]]; then
    python3 "$ROOT/quwoquan_ops/cli/lib/local_gamma_media.py" \
      materialize --target-root "$media"
    return 0
  fi
  echo "[local-gamma] FAIL: curated gamma media bundle is unavailable; sync ${LOCAL_GAMMA_MEDIA_ROOT} first" >&2
  return 1
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
    --gateway-base-url "$GATEWAY_BASE_URL" \
    --media-avatar-base-url "$MEDIA_AVATAR_BASE_URL" \
    --media-image-base-url "$MEDIA_IMAGE_BASE_URL" \
    --media-video-base-url "$MEDIA_VIDEO_BASE_URL" \
    --media-upload-base-url "$MEDIA_UPLOAD_BASE_URL"
}

preflight_local_gamma_inputs() {
  if [[ ! -d "$LOCAL_GAMMA_TAGS_DIR" ]]; then
    echo "[local-gamma] FAIL: missing canonical control-plane taxonomy: $LOCAL_GAMMA_TAGS_DIR" >&2
    return 1
  fi
  if [[ ! -f "$LOCAL_GAMMA_TAG_OBJECTS_FILE" ]]; then
    echo "[local-gamma] FAIL: missing object_tag_index fixture: $LOCAL_GAMMA_TAG_OBJECTS_FILE" >&2
    return 1
  fi
}

preflight_docker_storage() {
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  echo "[local-gamma] Docker storage snapshot before compose build:"
  if ! docker system df; then
    echo "[local-gamma] WARN: docker system df failed; compose build will report the concrete Docker error" >&2
  fi
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
  local_gamma_service_default_image_ref "$1"
}

validate_local_gamma_built_images() {
  local service=""
  local image_ref=""
  [[ "${podman_compose:-0}" == "1" ]] || return 0
  for service in "${compose_build_services[@]}"; do
    image_ref="$(expected_local_gamma_built_image_ref "$service" || true)"
    [[ -n "$image_ref" ]] || continue
    if ! podman image exists "$image_ref" >/dev/null 2>&1; then
      echo "[local-gamma] FAIL: expected podman image missing after build: $image_ref" >&2
      return 1
    fi
  done
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
  rm -f "$build_log"
  preflight_docker_storage
  ensure_local_gamma_base_images
  echo "[local-gamma] building services: ${compose_build_services[*]}"
  "${compose_cmd[@]}" build "${compose_build_services[@]}" 2>&1 | tee "$build_log" || build_status=$?
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
    rm -f "$build_log"
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

if [[ "$print_env" == "1" ]]; then
  # This is an introspection command. It must not render configuration, create
  # runtime output, touch Docker, or alter the currently running environment.
  print_defines
  exit 0
fi

if [[ "$down" == "1" ]]; then
  stop_colima_tunnels
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" down
  cleanup_stale_named_gamma_containers
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
  "${QWQ_OUTPUT_ROOT}/env/repo/local/control-plane/process/platform-ops-service"
validate_caddyfile_source

if [[ "$skip_up" == "1" ]]; then
  echo "[local-gamma] prepared artifacts only"
  echo "[local-gamma] configVersion=$CONFIG_VERSION imageVersion=$IMAGE_VERSION"
  exit 0
fi

if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  preflight_local_gamma_inputs
fi

podman_compose=0
if docker --version 2>/dev/null | grep -qi 'podman' && command -v podman-compose >/dev/null 2>&1; then
  podman_compose=1
  compose_cmd=(podman-compose -f "$COMPOSE_FILE" --podman-build-args=--pull=never --podman-run-args=--pull=never)
  compose_up_args=(up -d --no-build)
else
  compose_cmd=(docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE")
  compose_up_args=(up -d --remove-orphans)
  if [[ "$skip_build" == "1" ]]; then
    compose_up_args+=(--no-build)
  fi
fi

compose_build_services=(
  rec-model-service
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
if [[ ",${COMPOSE_PROFILES:-}," == *,edge-media,* ]]; then
  compose_build_services+=(rtc-service)
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
    quwoquan_service_rec-model-service_1 \
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
    --platform=linux/amd64 \
    --net "$network_name" --network-alias elasticsearch \
    -e discovery.type=single-node \
    -e xpack.security.enabled=false \
    -e xpack.security.http.ssl.enabled=false \
    -e ES_JAVA_OPTS='-Xms512m -Xmx512m' \
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

  podman run --pull=never --name quwoquan_service_rec-model-service_1 -d \
    --net "$network_name" --network-alias rec-model-service --network-alias recommendation-service \
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
  wait_healthy quwoquan_service_rec-model-service_1

  podman run --pull=never --name quwoquan_service_product-ops-service_1 -d \
    --net "$network_name" --network-alias product-ops-service \
    -e SERVICE_NAME=product-ops-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PRODUCT_OPS_SERVICE_ADDR=:18086 \
    -e MONGO_URI=mongodb://mongodb:27017 \
    -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e PRODUCT_OPS_REDIS_REC_ADDR=redis:6379 -e PRODUCT_OPS_REDIS_GENERAL_ADDR=redis:6379 \
    -e PRODUCT_OPS_SLS_REGION="${PRODUCT_OPS_SLS_REGION:?PRODUCT_OPS_SLS_REGION is required}" \
    -e PRODUCT_OPS_SLS_ENDPOINT="${PRODUCT_OPS_SLS_ENDPOINT:?PRODUCT_OPS_SLS_ENDPOINT is required}" \
    -e PRODUCT_OPS_SLS_PROJECT="${PRODUCT_OPS_SLS_PROJECT:?PRODUCT_OPS_SLS_PROJECT is required}" \
    -e ALIBABA_CLOUD_ACCESS_KEY_ID="${ALIBABA_CLOUD_ACCESS_KEY_ID:?ALIBABA_CLOUD_ACCESS_KEY_ID is required}" \
    -e ALIBABA_CLOUD_ACCESS_KEY_SECRET="${ALIBABA_CLOUD_ACCESS_KEY_SECRET:?ALIBABA_CLOUD_ACCESS_KEY_SECRET is required}" \
    -e ALIBABA_CLOUD_SECURITY_TOKEN="${ALIBABA_CLOUD_SECURITY_TOKEN:-}" \
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

  podman run --pull=never --name quwoquan_service_platform-ops-service_1 -d \
    --net "$network_name" --network-alias platform-ops-service \
    -e SERVICE_NAME=platform-ops-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
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
    -e CHAT_GROUP_AVATAR_CDN_BASE_URL="$MEDIA_BASE_URL" \
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
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e USER_SERVICE_ADDR=:18082 \
    -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_user \
    -e REDIS_ADDR=redis:6379 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${ROOT}/quwoquan_service/contracts/metadata/user:/contracts/metadata/user:ro" \
    -v "${ROOT}/quwoquan_service/services/user-service/internal/infrastructure/migration:/internal/infrastructure/migration:ro" \
    -p "${LOCAL_GAMMA_USER_PORT:-19210}:18082" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18082/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_USER_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_user-service_1

  podman run --pull=never --name quwoquan_service_integration-service_1 -d \
    --net "$network_name" --network-alias integration-service \
    -e SERVICE_NAME=integration-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e INTEGRATION_SERVICE_ADDR=:18086 \
    -e INTEGRATION_MONGO_URI=mongodb://mongodb:27017 -e INTEGRATION_MONGO_DATABASE=quwoquan_integration \
    -e INTEGRATION_LOCATION_BAIDU_AK="${LOCAL_GAMMA_BAIDU_AK:-}" \
    -e INTEGRATION_LOCATION_AMAP_KEY="${LOCAL_GAMMA_AMAP_KEY:-}" \
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

  podman run --pull=never --name quwoquan_service_assistant-service_1 -d \
    --net "$network_name" --network-alias assistant-service \
    -e SERVICE_NAME=assistant-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e ASSISTANT_SERVICE_ADDR=:18087 \
    -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_assistant \
    -e REDIS_GENERAL_ADDR=redis:6379 -e REDIS_REC_ADDR=redis:6379 \
    -e ASSISTANT_MODEL_PROVIDER="${ASSISTANT_MODEL_PROVIDER:-}" \
    -e ALLOW_DETERMINISTIC_BETA="${ALLOW_DETERMINISTIC_BETA:-}" \
    -e ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-}" \
    -e ASSISTANT_NOTIFICATION_BASE_URL=http://notification-service:18087 \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e ASSISTANT_SEARCH_PROVIDER="${ASSISTANT_SEARCH_PROVIDER:-}" \
    -e PERSONAL_ASSISTANT_MIMO_API_KEY="${PERSONAL_ASSISTANT_MIMO_API_KEY:-}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_ASSISTANT_PORT:-19230}:18087" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18087/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_assistant-service_1

  podman run --pull=never --name quwoquan_service_tag-service_1 -d \
    --net "$network_name" --network-alias tag-service \
    -e SERVICE_NAME=tag-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e TAG_SERVICE_ADDR=:18092 \
    -e TAG_MONGO_URI=mongodb://mongodb:27017 -e TAG_MONGO_DATABASE=quwoquan_tag \
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
    -e LOCAL_GAMMA_TLS_MODE="${LOCAL_GAMMA_TLS_MODE:-internal}" \
    -v "${LOCAL_GAMMA_CADDYFILE}:/etc/caddy/Caddyfile:ro" \
    -v "${LOCAL_GAMMA_MEDIA_ROOT}:/srv/media:ro" \
    -v "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}:/srv/legal:ro" \
    -v "${LOCAL_GAMMA_CADDY_DATA_VOLUME}:/data" \
    -v "${LOCAL_GAMMA_CADDY_CONFIG_VOLUME}:/config" \
    -p "${LOCAL_GAMMA_HTTP_PORT:-19000}:443" \
    -p "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}:443" \
    -p "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}:443" \
    -p "${LOCAL_GAMMA_ADMIN_PORT:-2019}:2019" \
    --healthcheck-command "wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 5s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CADDY_IMAGE" >/dev/null
  wait_healthy quwoquan_service_gamma-proxy_1
else
  echo "[local-gamma] startup mode: compose-up"
  # Recreate the local mirror on every gate run so changed host port envs take effect.
  "${compose_cmd[@]}" down --remove-orphans >/dev/null 2>&1 || true
  cleanup_stale_named_gamma_containers
  # 本地进程中断时 Caddy 可能留下半写入的证书锁。此处代理已停止，
  # 可安全清理过期签发锁，同时保留本地 CA 与已签发证书。
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
  ensure_docker_gamma_proxy_started() {
    local name="quwoquan_service-gamma-proxy-1"
    local status=""
    local health=""
    local deadline=$((SECONDS + 15))
    while (( SECONDS < deadline )); do
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
    if [[ "${created_count:-0}" == "0" || "${running_count:-0}" != "0" ]]; then
      return 1
    fi
    echo "[local-gamma] compose left ${created_count} created-only containers; retrying once from the already-built images" >&2
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
    "${compose_cmd[@]}" "${retry_args[@]}"
  }
  if ! "${compose_cmd[@]}" "${compose_up_args[@]}"; then
    if retry_compose_up_after_created_only_failure; then
      echo "[local-gamma] compose created-only retry recovered startup"
    else
      echo "[local-gamma] FAIL: compose up failed; runtime readiness cannot be inferred from partial containers" >&2
      exit 1
    fi
  fi
  ensure_docker_gamma_proxy_started
fi
start_colima_tunnels_if_needed
ensure_public_hosts_mapping

# docker compose 分支不会逐项 wait_healthy；在宣告就绪前用主机侧探测避免 T3/T4 撞到端口未监听。
gamma_canonical_video_range_mime_ready() {
  local host="$1"
  local port="$2"
  local probe=""
  local status=""
  local content_type=""
  probe="$(
    curl -kfsS \
      --resolve "${host}:${port}:127.0.0.1" \
      -H "Range: bytes=0-1" \
      -o /dev/null \
      -w '%{http_code}|%{content_type}' \
      "https://${host}:${port}/media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
  )" || return 1
  status="${probe%%|*}"
  content_type="${probe#*|}"
  [[ "$status" == "206" && "$content_type" == video/* ]]
}

wait_local_gamma_host_ready() {
  local gw="${GATEWAY_BASE_URL%/}"
  local gw_host="gamma-api.quwoquan-env.test"
  local gw_port="${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local product_ops_host="gamma-product-ops.quwoquan-env.test"
  local product_ops_public_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local media_host="gamma-image.quwoquan-env.test"
  local video_host="gamma-video.quwoquan-env.test"
  local media_edge_port="${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  local po_port="${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}"
  local platform_ops_port="${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-19260}"
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local integration_port="${LOCAL_GAMMA_INTEGRATION_PORT:-19310}"
  local notification_port="${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}"
  local deadline=$(( $(date +%s) + HOST_READY_TIMEOUT_SECONDS ))
  local last_gamma_proxy_retry=0
  echo "[local-gamma] waiting for host probes (${HOST_READY_TIMEOUT_SECONDS}s): ${gw}/healthz + ${PRODUCT_OPS_BASE_URL%/}/healthz + ${MEDIA_BASE_URL%/}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png + ${MEDIA_VIDEO_BASE_URL%/}/media/video/s/video-primary-0001/post/video-content-0001/source.mp4(Range 206/video/*) + internal health"
  while (( $(date +%s) < deadline )); do
    if (( $(date +%s) - last_gamma_proxy_retry >= 15 )); then
      ensure_docker_gamma_proxy_started || true
      last_gamma_proxy_retry=$(date +%s)
    fi
    if curl -kfsS --resolve "${gw_host}:${gw_port}:127.0.0.1" "https://${gw_host}:${gw_port}/healthz" >/dev/null 2>&1 \
      && curl -kfsS --resolve "${product_ops_host}:${product_ops_public_port}:127.0.0.1" "https://${product_ops_host}:${product_ops_public_port}/healthz" >/dev/null 2>&1 \
      && curl -kfsS --resolve "${media_host}:${media_edge_port}:127.0.0.1" "https://${media_host}:${media_edge_port}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" >/dev/null 2>&1 \
      && gamma_canonical_video_range_mime_ready "$video_host" "$media_edge_port" \
      && curl -fsS "http://127.0.0.1:${po_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${platform_ops_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${user_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${integration_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${notification_port}/healthz" >/dev/null 2>&1
    then
      return 0
    fi
    sleep 2
  done
  echo "[local-gamma] FAIL: host cannot reach the canonical media video Range/MIME surface or required health probes within ${HOST_READY_TIMEOUT_SECONDS}s" >&2
  curl -kfsS --resolve "${gw_host}:${gw_port}:127.0.0.1" "https://${gw_host}:${gw_port}/healthz" >&2 || true
  curl -kfsS --resolve "${product_ops_host}:${product_ops_public_port}:127.0.0.1" "https://${product_ops_host}:${product_ops_public_port}/healthz" >&2 || true
  curl -kfsS --resolve "${media_host}:${media_edge_port}:127.0.0.1" "https://${media_host}:${media_edge_port}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" >&2 || true
  gamma_canonical_video_range_mime_ready "$video_host" "$media_edge_port" || true
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" ps >&2 || true
  curl -fsS "http://127.0.0.1:${integration_port}/healthz" >&2 || true
  curl -fsS "http://127.0.0.1:${notification_port}/healthz" >&2 || true
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail 80 gamma-proxy product-ops-service platform-ops-service user-service integration-service notification-service >&2 || true
  return 1
}
wait_local_gamma_host_ready

export_local_gamma_root_ca() {
  local container_name=""
  local destination="${QWQ_DEPLOY_WORK_ROOT}/gamma-local/certificates/root.crt"
  for candidate in quwoquan_service-gamma-proxy-1 quwoquan_service_gamma-proxy_1; do
    if docker inspect "$candidate" >/dev/null 2>&1 || podman inspect "$candidate" >/dev/null 2>&1; then
      container_name="$candidate"
      break
    fi
  done
  if [[ -z "$container_name" ]]; then
    echo "[local-gamma] FAIL: gamma proxy container unavailable for CA export" >&2
    return 1
  fi
  mkdir -p "$(dirname "$destination")"
  if docker cp "${container_name}:/data/caddy/pki/authorities/local/root.crt" "$destination" >/dev/null 2>&1 \
    || podman cp "${container_name}:/data/caddy/pki/authorities/local/root.crt" "$destination" >/dev/null 2>&1; then
    if [[ -z "${LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE:-}" || ! -f "${LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE}" ]]; then
      echo "[local-gamma] FAIL: object-storage CA is unavailable for local trust export" >&2
      return 1
    fi
    cat "${LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE}" >> "$destination"
    chmod 0644 "$destination"
    echo "[local-gamma] exported local trust root: $destination"
    return 0
  fi
  echo "[local-gamma] FAIL: Caddy local root CA export failed" >&2
  return 1
}
export_local_gamma_root_ca

seed_integration_location_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local fixture="$ROOT/quwoquan_service/contracts/metadata/integration/test_fixtures/scenarios/integration_scenarios.json"
  if [[ -z "$mongo_port" || ! -f "$fixture" ]]; then
    echo "[local-gamma] FAIL: Integration Location seed input is unavailable" >&2
    return 1
  fi
  python3 - "$fixture" "$mongo_port" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

fixture_path, mongo_port = sys.argv[1:3]
payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
raw_items = payload.get("seedSets", {}).get("location_poi_core", {}).get("pois", [])
documents = []
for raw in raw_items:
    poi_id = str(raw.get("poiId", "")).strip()
    name = str(raw.get("name", "")).strip()
    latitude = raw.get("lat")
    longitude = raw.get("lng")
    if not poi_id or not name or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise SystemExit("Integration Location fixture contains an incomplete POI")
    documents.append(
        {
            "poiId": poi_id,
            "name": name,
            "address": str(raw.get("address", "")),
            "cityCode": str(raw.get("cityCode", "")),
            "adCode": str(raw.get("adCode", "")),
            "distanceMeters": int(raw.get("distanceMeters", 0) or 0),
            "location": {
                "type": "Point",
                "coordinates": [float(longitude), float(latitude)],
            },
        }
    )
if not documents:
    raise SystemExit("Integration Location fixture is empty")
encoded = json.dumps(documents, ensure_ascii=False)
script = f"""
const collection = db.getSiblingDB('quwoquan_integration').location_pois;
collection.deleteMany({{}});
collection.insertMany({encoded});
printjson({{inserted: collection.countDocuments({{}})}});
"""
result = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=script,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if result.returncode != 0:
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    raise SystemExit(result.returncode)
print(result.stdout.strip())
PY
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_integration_location_data
else
  echo "[local-gamma] skip Integration Location seed because STAGE=${STAGE} uses persisted/host data"
fi

# tag-service 数据在 local-gamma 启动时按当前真相源重建：
#  - tag_nodes ← control_plane/governance/taxonomy（路径制 taxonomy 唯一真相源）
#  - object_tag_index ← contracts/metadata/tag 的 contract fixture（与契约测试/app mock 同源）
# local-gamma 尚未上线；这里直接清库重建，拒绝保留任何旧索引名、旧数据或兼容路径。
seed_tag_service_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_MONGO_PORT is required for tag data seed" >&2
    return 1
  fi
  local mongo_uri="mongodb://127.0.0.1:${mongo_port}/?directConnection=true"
  local data_release_id="${LOCAL_GAMMA_DATA_RELEASE_ID:-local-gamma-tag-seed}"
  echo "[local-gamma] rebuilding ${LOCAL_GAMMA_TAG_DB} from current tag sources ..."
  mongosh "$mongo_uri" --quiet --eval "db.getSiblingDB(\"${LOCAL_GAMMA_TAG_DB}\").dropDatabase()"
  echo "[local-gamma] seeding tag_nodes (${LOCAL_GAMMA_TAGS_DIR} -> ${LOCAL_GAMMA_TAG_DB}.tag_nodes) ..."
  ( cd "$ROOT/quwoquan_service" && go run ./services/tag-service/cmd/import \
      --tags-dir "$LOCAL_GAMMA_TAGS_DIR" \
      --mongo-uri "$mongo_uri" --db "$LOCAL_GAMMA_TAG_DB" \
      --release-id "$data_release_id" --source-owner fixture )
  echo "[local-gamma] seeding object_tag_index (${LOCAL_GAMMA_TAG_OBJECTS_FILE} -> ${LOCAL_GAMMA_TAG_DB}.object_tag_index) ..."
  ( cd "$ROOT/quwoquan_service" && go run ./services/tag-service/cmd/import-objects \
      --objects-file "$LOCAL_GAMMA_TAG_OBJECTS_FILE" \
      --mongo-uri "$mongo_uri" --db "$LOCAL_GAMMA_TAG_DB" \
      --release-id "$data_release_id" --source-owner fixture )
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_tag_service_data
else
  echo "[local-gamma] skip tag seed because STAGE=${STAGE} uses persisted/host data"
fi

seed_gamma_content_data() {
  echo "[local-gamma] seeding content posts (gamma curated manifest) ..."
  if ! python3 - <<'PY' >/dev/null 2>&1; then
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    echo "[local-gamma] GATE_BLOCK: content seed requires python3 >= 3.10" >&2
    return 1
  fi
  if ! python3 "$ROOT/quwoquan_app/scripts/gamma/run_local_gamma_t3.py" --seed-only --report "${GAMMA_RUN_ROOT}/content-seed-report.json"; then
    echo "[local-gamma] GATE_BLOCK: content seed failed; home/discovery feeds are not valid without it" >&2
    return 1
  fi
  echo "[local-gamma] content seed completed"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_gamma_content_data
else
  echo "[local-gamma] skip content seed because STAGE=${STAGE} uses persisted/host data"
fi

seed_gamma_intersection_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local gateway="${GATEWAY_BASE_URL%/}"
  local report="${GAMMA_RUN_ROOT}/intersection-seed-report.json"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] GATE_BLOCK: intersection seed requires LOCAL_GAMMA_MONGO_PORT" >&2
    return 1
  fi
  echo "[local-gamma] seeding intersection viewer relationships and read model ..."
  if ! python3 - "$ROOT" "$mongo_port" "$gateway" "$report" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root, mongo_port, gateway, report_path = sys.argv[1:5]
sys.path.insert(0, root)

from quwoquan_ops.cli.lib.local_gamma_auth import (
    open_local_gamma_acceptance_session,
    request_local_gamma_json,
)

session = open_local_gamma_acceptance_session(gateway)
viewer = session.persona_id
person = "sys_travel_9003_sub_01"
third_a = "sys_travel_9004_sub_01"
third_b = "sys_travel_9005_sub_01"
circle = "fixture_circle_photo"
entity = "fixture_homepage_travel_photo_west_lake"
shared_post = "gamma_intersection_shared_post"
profile_post = "gamma_intersection_profile_post"
avatar = (
    "https://gamma-image.quwoquan-env.test:19100/media/avatar/s/"
    "archived-avatar/user/fixture_user_photo/v1/avatar.png"
)

seed_js = f"""
const db = db.getSiblingDB('quwoquan_content');
const viewer = '{viewer}';
const person = '{person}';
const thirdA = '{third_a}';
const thirdB = '{third_b}';
const circle = '{circle}';
const entity = '{entity}';
const sharedPost = '{shared_post}';
const profilePost = '{profile_post}';
const avatar = '{avatar}';
const now = new Date();
db.follow_edges.deleteMany({{$or:[{{followerId: {{$in:[viewer, person]}}}}, {{followeeId: {{$in:[viewer, person]}}}}]}});
db.circle_members.deleteMany({{userId: {{$in:[viewer, person]}}}});
db.rm_behavior_events.deleteMany({{userId: {{$in:[viewer, person, thirdA]}}}});
db.entity_wishlist_events.deleteMany({{userId: {{$in:[viewer, person]}}}});
db.rec_learning_events.deleteMany({{userId: {{$in:[thirdA, thirdB]}}, contentId: sharedPost}});
db.rm_recommend_feature.deleteMany({{userId: {{$in:[thirdA, thirdB]}}}});
db.circle_tag_aggregates.deleteMany({{circleId: circle}});
db.posts.deleteMany({{postId: {{$in:[sharedPost, profilePost]}}}});
db.rm_viewer_object_intersection.deleteMany({{_id: viewer}});
db.follow_edges.insertMany([
  {{followerId: viewer, followeeId: thirdA, createdAt: now}},
  {{followerId: viewer, followeeId: thirdB, createdAt: now}},
  {{followerId: viewer, followeeId: person, createdAt: now}},
  {{followerId: person, followeeId: thirdA, createdAt: now}},
  {{followerId: person, followeeId: thirdB, createdAt: now}},
  {{followerId: thirdA, followeeId: person, createdAt: now}}
]);
db.circle_members.insertMany([
  {{circleId: circle, userId: viewer, role: 'member', joinedAt: now, lastActiveAt: now}},
  {{circleId: circle, userId: person, role: 'member', joinedAt: now, lastActiveAt: now}}
]);
db.rm_behavior_events.insertMany([
  {{userId: viewer, action: 'comment', contentId: sharedPost, entityRefs: [], createdAt: now}},
  {{userId: person, action: 'comment', contentId: sharedPost, entityRefs: [], createdAt: now}},
  {{userId: viewer, action: 'entity_page_view', contentId: '', entityRefs: [entity], createdAt: now}},
  {{userId: person, action: 'entity_page_view', contentId: '', entityRefs: [entity], createdAt: now}},
  {{userId: thirdA, action: 'entity_page_view', contentId: '', entityRefs: [entity], createdAt: now}}
]);
db.entity_wishlist_events.insertMany([
  {{userId: viewer, entityId: entity, objectType: 'sight', displayName: '西湖旅行摄影线', status: 'active', createdAt: now}},
  {{userId: person, entityId: entity, objectType: 'sight', displayName: '西湖旅行摄影线', status: 'active', createdAt: now}}
]);
db.rec_learning_events.insertMany([
  {{userId: thirdA, eventType: 'rec_engagement', contentId: sharedPost, labels: {{action: 'like'}}, createdAt: now}},
  {{userId: thirdB, eventType: 'rec_engagement', contentId: sharedPost, labels: {{action: 'share'}}, createdAt: now}}
]);
db.rm_recommend_feature.insertMany([
  {{userId: thirdA, userFeatures: {{tagInteraction: {{'Topic/摄影': 2, 'Topic/旅行/玩法/摄影旅拍': 1}}}}, updatedAt: now}},
  {{userId: thirdB, userFeatures: {{tagInteraction: {{'Topic/摄影': 3, 'Topic/旅行/玩法/摄影旅拍': 1}}}}, updatedAt: now}}
]);
db.circle_tag_aggregates.insertOne({{
  circleId: circle,
  tags: {{'Topic/摄影': 4.5, 'Topic/旅行/玩法/摄影旅拍': 3.5, 'Topic/城市漫步': 2.5}},
  updatedAt: now
}});
db.posts.insertMany([
  {{_id: profilePost, postId: profilePost, id: profilePost, authorId: person, status: 'published', authorDisplayNameSnapshot: '交集约伴体验号', authorAvatarUrlSnapshot: avatar, updatedAt: now, publishedAt: now}},
  {{_id: sharedPost, postId: sharedPost, id: sharedPost, authorId: person, status: 'published', title: '交集真实证据共享内容', contentType: 'article', authorDisplayNameSnapshot: '交集约伴体验号', authorAvatarUrlSnapshot: avatar, updatedAt: now, publishedAt: now}}
]);
printjson({{viewer, person, circle, entity}});
"""
seed = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=seed_js,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if seed.returncode != 0:
    print(seed.stdout)
    print(seed.stderr, file=sys.stderr)
    raise SystemExit(seed.returncode)

def request_json(path: str) -> dict:
    return request_local_gamma_json(
        gateway,
        path=path,
        session=session,
    )

object_body = request_json(
    f"/content/intersections/object?objectId={person}&objectType=user&limit=8"
)
reasons = object_body.get("items") or []
if not reasons:
    raise SystemExit("object intersection seed probe returned no items")

materialize_js = f"""
const viewer = '{viewer}';
const reasons = {json.dumps(reasons, ensure_ascii=False)};
db.getSiblingDB('quwoquan_content').rm_viewer_object_intersection.updateOne(
  {{_id: viewer}},
  {{$set: {{computedAt: new Date(), reasonsJson: JSON.stringify(reasons)}}}},
  {{upsert: true}}
);
printjson({{viewer, reasonCount: reasons.length}});
"""
materialize = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=materialize_js,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if materialize.returncode != 0:
    print(materialize.stdout)
    print(materialize.stderr, file=sys.stderr)
    raise SystemExit(materialize.returncode)

summary = request_json("/content/intersections/summary")
listing = request_json("/content/intersections?limit=8")
if int(summary.get("totalCount") or 0) <= 0:
    raise SystemExit(f"intersection summary remains empty: {summary}")
if len(listing.get("items") or []) <= 0:
    raise SystemExit(f"intersection list remains empty: {listing}")

report = {
    "authenticatedProbe": True,
    "personObjectId": person,
    "entityObjectId": entity,
    "summaryTotalCount": summary.get("totalCount"),
    "summaryDimensions": [
        item.get("dimension")
        for item in summary.get("dimensions", [])
        if isinstance(item, dict)
    ],
    "listItemCount": len(listing.get("items") or []),
    "objectPointSources": [
        point.get("sourceRef")
        for item in reasons
        for point in item.get("intersectionPoints", [])
        if isinstance(point, dict)
    ],
}
Path(report_path).parent.mkdir(parents=True, exist_ok=True)
Path(report_path).write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, ensure_ascii=False))
PY
  then
    echo "[local-gamma] GATE_BLOCK: intersection seed failed; /content/intersections is unproven" >&2
    return 1
  fi
  echo "[local-gamma] intersection seed completed (${report})"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_gamma_intersection_data
else
  echo "[local-gamma] skip intersection seed because STAGE=${STAGE} uses persisted/host data"
fi

seed_gamma_premium_pool_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local gateway="${GATEWAY_BASE_URL%/}"
  local report="${GAMMA_RUN_ROOT}/premium-pool-seed-report.json"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] GATE_BLOCK: premium pool seed requires LOCAL_GAMMA_MONGO_PORT" >&2
    return 1
  fi
  echo "[local-gamma] seeding premium pool projection and recall proof ..."
  if ! python3 - "$ROOT" "$mongo_port" "$gateway" "$report" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root, mongo_port, gateway, report_path = sys.argv[1:5]
sys.path.insert(0, root)

from quwoquan_ops.cli.lib.local_gamma_auth import (
    open_local_gamma_acceptance_session,
    request_local_gamma_json,
)

run_id = Path(report_path).parent.name
session = open_local_gamma_acceptance_session(
    gateway,
    subject=f"premium-pool-seed-{run_id}",
)
eligible = "gamma_premium_pool_eligible_post"
expired = "gamma_premium_pool_expired_post"
rolled_back = "gamma_premium_pool_rolled_back_post"
takedown = "gamma_premium_pool_takedown_post"
all_ids = [eligible, expired, rolled_back, takedown]
cover = (
    "https://gamma-image.quwoquan-env.test:19100/media/image/s/"
    "archived-image/post/fixture_photo_001/v1/cover.png"
)

seed_js = f"""
const db = db.getSiblingDB('quwoquan_content');
const now = new Date();
const future = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
const past = new Date(now.getTime() - 60 * 60 * 1000);
const ids = {json.dumps(all_ids)};
db.posts.deleteMany({{_id: {{$in: ids}}}});
db.rm_discovery_feed.deleteMany({{postId: {{$in: ids}}}});
db.rm_premium_pool.deleteMany({{contentId: {{$in: ids}}}});
for (const id of ids) {{
  db.posts.insertOne({{
    _id: id,
    postId: id,
    id: id,
    contentType: 'image',
    contentIdentity: 'work',
    title: id === '{eligible}' ? 'Gamma 精品池真实召回样例' : `Gamma 精品池不可召回样例 ${{id}}`,
    body: 'premium pool gamma seed',
    mediaUrls: ['{cover}'],
    coverUrl: '{cover}',
    thumbnailUrl: '{cover}',
    authorId: 'sys_travel_9003_sub_01',
    authorDisplayNameSnapshot: '交集约伴体验号',
    status: 'published',
    visibility: 'public',
    likeCount: 12,
    commentCount: 3,
    shareCount: 1,
    createdAt: now,
    updatedAt: now,
    publishedAt: now
  }});
  db.rm_discovery_feed.insertOne({{
    postId: id,
    contentType: 'image',
    authorId: 'sys_travel_9003_sub_01',
    title: id,
    tagRefs: ['Topic/旅行', 'Topic/摄影'],
    entityRefs: ['fixture_homepage_travel_photo_west_lake'],
    coverUrl: '{cover}',
    likeCount: 12,
    commentCount: 3,
    shareCount: 1,
    viewCount: 180,
    publishedAt: now,
    recScore: id === '{eligible}' ? 0.96 : 0.2,
    qualityScore: id === '{eligible}' ? 0.96 : 0.2,
    contentVertical: 'travel_photography',
    supplySource: 'product_ops'
  }});
}}
db.rm_premium_pool.insertMany([
  {{
    contentId: '{eligible}',
    scope: 'global',
    status: 'active',
    eligibilityState: 'eligible',
    ineligibleReasons: [],
    qualityAdmission: 'approved',
    qualityScore: 0.96,
    supplySource: 'product_ops',
    sourceTaskId: 'gamma_premium_pool_seed',
    auditId: 'audit_gamma_premium_eligible',
    rollbackToken: 'rbk_gamma_premium_eligible',
    featuredAt: now,
    expiresAt: future,
    takedownEjected: false,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }},
  {{
    contentId: '{expired}',
    scope: 'global',
    status: 'active',
    eligibilityState: 'ineligible',
    ineligibleReasons: ['expired'],
    qualityAdmission: 'approved',
    qualityScore: 0.95,
    supplySource: 'product_ops',
    featuredAt: now,
    expiresAt: past,
    takedownEjected: false,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }},
  {{
    contentId: '{rolled_back}',
    scope: 'global',
    status: 'rolled_back',
    eligibilityState: 'ineligible',
    ineligibleReasons: ['inactive_status'],
    qualityAdmission: 'approved',
    qualityScore: 0.94,
    supplySource: 'product_ops',
    featuredAt: now,
    expiresAt: future,
    takedownEjected: false,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }},
  {{
    contentId: '{takedown}',
    scope: 'global',
    status: 'takedown_ejected',
    eligibilityState: 'ineligible',
    ineligibleReasons: ['takedown_ejected'],
    qualityAdmission: 'approved',
    qualityScore: 0.93,
    supplySource: 'product_ops',
    featuredAt: now,
    expiresAt: future,
    takedownEjected: true,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }}
]);
printjson({{eligible: '{eligible}', ineligible: ['{expired}', '{rolled_back}', '{takedown}']}});
"""
seed = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=seed_js,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if seed.returncode != 0:
    print(seed.stdout)
    print(seed.stderr, file=sys.stderr)
    raise SystemExit(seed.returncode)

body = request_local_gamma_json(
    gateway,
    path="/content/feed?type=premium&limit=5",
    session=session,
)
items = body.get("items") or []
ids = [item.get("id") or item.get("postId") for item in items if isinstance(item, dict)]
if eligible not in ids:
    raise SystemExit(f"premium pool eligible item missing from feed: ids={ids}")
blocked = [item for item in (expired, rolled_back, takedown) if item in ids]
if blocked:
    raise SystemExit(f"ineligible premium pool items leaked into feed: {blocked}")
recall_paths = {
    (item.get("id") or item.get("postId")): item.get("recallPath")
    for item in items
    if isinstance(item, dict)
}
if recall_paths.get(eligible) != "premium_pool":
    raise SystemExit(f"eligible recallPath must be premium_pool, got {recall_paths.get(eligible)!r}")

report = {
    "authenticatedProbe": True,
    "eligibleContentId": eligible,
    "ineligibleContentIds": [expired, rolled_back, takedown],
    "feedItemIds": ids,
    "eligibleRecallPath": recall_paths.get(eligible),
}
Path(report_path).parent.mkdir(parents=True, exist_ok=True)
Path(report_path).write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, ensure_ascii=False))
PY
  then
    echo "[local-gamma] GATE_BLOCK: premium pool seed failed; premium stream recall is unproven" >&2
    return 1
  fi
  echo "[local-gamma] premium pool seed completed (${report})"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_gamma_premium_pool_data
else
  echo "[local-gamma] skip premium pool seed because STAGE=${STAGE} uses persisted/host data"
fi

# search-service 的 ES 召回读模型 cold-start：把已 seed 的内容（quwoquan_content.posts）
# 经统一投影回填进共享 ES 索引 quwoquan_objects（与 search-service 查询同一索引）。
# 这是检索读模型的环境 seed，与 tag/content seed 同级，保证 /search 返回真实 hit。
seed_search_index() {
  local es_port="${LOCAL_GAMMA_ES_PORT:-}"
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  if [[ -z "$es_port" || -z "$mongo_port" ]]; then
    echo "[local-gamma] FAIL: search backfill requires LOCAL_GAMMA_ES_PORT and LOCAL_GAMMA_MONGO_PORT" >&2
    return 1
  fi
  echo "[local-gamma] waiting for ES host port ${es_port} (yellow) before search backfill ..."
  if ! python3 - "$es_port" <<'PY'
import sys
import time
import urllib.request

port = sys.argv[1]
deadline = time.time() + 120
last = None
ok = False
while time.time() < deadline:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/_cluster/health?wait_for_status=yellow&timeout=2s",
            timeout=4,
        ) as resp:
            if 200 <= int(resp.status) < 300:
                ok = True
                break
            last = f"http {resp.status}"
    except Exception as exc:  # noqa: BLE001
        last = str(exc)
    time.sleep(2)
raise SystemExit(0 if ok else (last or "es not ready"))
PY
  then
    echo "[local-gamma] FAIL: ES host port ${es_port} is not ready for search backfill" >&2
    return 1
  fi
  echo "[local-gamma] backfilling search index (quwoquan_content.posts -> ES quwoquan_objects) ..."
  # batch-size 100：本地 ES 跑在 linux/amd64 模拟（Apple Silicon 无原生 8.x JDK），
  # 单节点写入吞吐受限；ES client RequestTimeout 默认 5s，500-doc 默认批的单次 _bulk
  # 会超时（服务端仍写入但 client 报 context deadline exceeded）。按 100/批切分后每个
  # _bulk 都在 5s 内返回，回填稳定干净成功（这是 backfill 暴露 --batch-size 的用途，
  # 非 shim：换原生 ES 集群时该值不影响正确性，只影响往返次数）。
  if ! ( cd "$ROOT/quwoquan_service" && SEARCH_ES_ENDPOINTS="http://127.0.0.1:${es_port}" \
      go run ./services/content-service/cmd/search-backfill \
      --mongo-uri "mongodb://127.0.0.1:${mongo_port}/?directConnection=true" \
      --posts-db quwoquan_content --env gamma --batch-size 100 \
      --request-timeout "$LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT" ); then
    echo "[local-gamma] FAIL: search backfill failed; gamma startup is blocked because /search would be incomplete" >&2
    return 1
  fi
  echo "[local-gamma] search index backfill completed"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_search_index
else
  echo "[local-gamma] skip search backfill because STAGE=${STAGE} uses persisted/host data"
fi

python3 - "$stack_report" "$CONFIG_VERSION" "$IMAGE_VERSION" "$PREVIOUS_IMAGE_VERSION" "$STAGE" "$LOCAL_GAMMA_APP_ENV" "$CONFIG_SOURCE_ENV" "$GATEWAY_BASE_URL" "$PRODUCT_OPS_BASE_URL" "$MEDIA_BASE_URL" "$restarted_from_previous" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    report_path,
    config_version,
    image_version,
    previous_image_version,
    stage,
    runtime_env,
    config_env,
    gateway,
    product_ops,
    media,
    restarted,
) = sys.argv[1:12]
payload = {
    "status": "passed",
    "serviceMode": "single-stack",
    "restartedFromPrevious": restarted == "1",
    "stage": stage,
    "configVersion": config_version,
    "imageVersion": image_version,
    "previousImageVersion": previous_image_version or None,
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
echo "[local-gamma] media-edge: $MEDIA_BASE_URL"
echo "[local-gamma] dart defines:"
print_defines
