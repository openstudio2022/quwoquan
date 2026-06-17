#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
COMPOSE_FILE="$ROOT/quwoquan_service/docker-compose.gamma-local.yaml"
if [[ -z "${LOCAL_GAMMA_HTTP_PORT:-}" \
   || -z "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_PLATFORM_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-}" \
   || -z "${LOCAL_GAMMA_MEDIA_ORIGIN_PORT:-}" \
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
   || -z "${LOCAL_GAMMA_POSTGRES_PORT:-}" \
   || -z "${LOCAL_GAMMA_MONGO_PORT:-}" \
   || -z "${LOCAL_GAMMA_REDIS_PORT:-}" \
   || -z "${LOCAL_GAMMA_ES_PORT:-}" ]]; then
  eval "$(python3 "$ROOT/agent_ops/deploy/print_local_port_profile.py" --profile gamma-local --format shell-defaults)"
fi
# docker compose 只读取导出的环境变量；这里把 canonical local-gamma 端口全部导出，
# 避免直接运行脚本/Makefile 时回退到 compose 文件里的旧默认端口。
export \
  LOCAL_GAMMA_HTTP_PORT \
  LOCAL_GAMMA_PRODUCT_OPS_PORT \
  LOCAL_GAMMA_PLATFORM_OPS_PORT \
  LOCAL_GAMMA_MEDIA_EDGE_PORT \
  LOCAL_GAMMA_MEDIA_ORIGIN_PORT \
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
  LOCAL_GAMMA_POSTGRES_PORT \
  LOCAL_GAMMA_MONGO_PORT \
  LOCAL_GAMMA_MONGO_CACHE_SIZE_GB \
  LOCAL_GAMMA_REDIS_PORT \
  LOCAL_GAMMA_ES_PORT
CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-local-gamma-v1}"
IMAGE_VERSION="${LOCAL_GAMMA_IMAGE_VERSION:-0.0.1}"
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-http://127.0.0.1:${LOCAL_GAMMA_HTTP_PORT}}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-http://127.0.0.1:${LOCAL_GAMMA_PRODUCT_OPS_PORT}}"
MEDIA_BASE_URL="${LOCAL_GAMMA_MEDIA_PUBLIC_BASE_URL:-${LOCAL_GAMMA_MEDIA_BASE_URL:-http://127.0.0.1:${LOCAL_GAMMA_MEDIA_EDGE_PORT}}}"
MEDIA_ORIGIN_BASE_URL="${LOCAL_GAMMA_MEDIA_ORIGIN_BASE_URL:-}"
LOCAL_MEDIA_ORIGIN_URL="http://127.0.0.1:${LOCAL_GAMMA_MEDIA_ORIGIN_PORT}"
LOCAL_GAMMA_TAGS_DIR="${LOCAL_GAMMA_TAGS_DIR:-$ROOT/quwoquan_data/publish/tags}"
LOCAL_GAMMA_TAG_OBJECTS_FILE="${LOCAL_GAMMA_TAG_OBJECTS_FILE:-$ROOT/quwoquan_service/contracts/metadata/tag/test_fixtures/scenarios/tag_scenarios.json}"
LOCAL_GAMMA_TAG_DB="${LOCAL_GAMMA_TAG_DB:-quwoquan_tag}"
# 2G onebox 在 gray/prod 切换窗口会短时双栈并存；显式压低 Mongo cache，避免数据面被 OOM kill。
LOCAL_GAMMA_MONGO_CACHE_SIZE_GB="${LOCAL_GAMMA_MONGO_CACHE_SIZE_GB:-0.25}"
# daocloud 镜像代理在部分网络下会 EOF；默认直连 Docker Hub，可通过环境变量覆盖。
DOCKER_LIBRARY_PREFIX="${LOCAL_GAMMA_DOCKER_LIBRARY_PREFIX:-docker.io/library}"
HOST_READY_TIMEOUT_SECONDS="${LOCAL_GAMMA_HOST_READY_TIMEOUT_SECONDS:-360}"
FORCE_CLEAN_RECREATE="${LOCAL_GAMMA_FORCE_CLEAN_RECREATE:-0}"
PRESERVE_POSTGRES_VOLUME="${LOCAL_GAMMA_PRESERVE_POSTGRES_VOLUME:-0}"
LOCAL_GAMMA_STATE_ROOT="${LOCAL_GAMMA_STATE_ROOT:-$ROOT/state/local/gamma}"
LOCAL_GAMMA_ARTIFACT_ROOT="${LOCAL_GAMMA_ARTIFACT_ROOT:-$ROOT/artifacts/local-gamma}"
LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_STATE_ROOT}/config-root"
LOCAL_GAMMA_MEDIA_ROOT="${LOCAL_GAMMA_STATE_ROOT}/media"
LOCAL_GAMMA_CADDYFILE="${LOCAL_GAMMA_STATE_ROOT}/Caddyfile"
LOCAL_GAMMA_MODEL_CACHE_ROOT="${LOCAL_GAMMA_STATE_ROOT}/model-cache"
LOCAL_GAMMA_STACK_REPORT="${LOCAL_GAMMA_STATE_ROOT}/stack_state.json"
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
    tag-service) echo "localhost/quwoquan_service_tag-service:latest" ;;
    search-service) echo "localhost/quwoquan_service_search-service:latest" ;;
    entity-service) echo "localhost/quwoquan_service_entity-service:latest" ;;
    circle-service) echo "localhost/quwoquan_service_circle-service:latest" ;;
    rtc-service) echo "localhost/quwoquan_service_rtc-service:latest" ;;
    *) return 1 ;;
  esac
}

local_gamma_service_repository_name() {
  case "$1" in
    rec-model-service) echo "recommendation-service" ;;
    content-service|chat-service|user-service|assistant-service|product-ops-service|tag-service|search-service|entity-service|circle-service|rtc-service) echo "$1" ;;
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
export LOCAL_GAMMA_TAG_SERVICE_IMAGE="${LOCAL_GAMMA_TAG_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref tag-service)}"
export LOCAL_GAMMA_SEARCH_SERVICE_IMAGE="${LOCAL_GAMMA_SEARCH_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref search-service)}"
export LOCAL_GAMMA_ENTITY_SERVICE_IMAGE="${LOCAL_GAMMA_ENTITY_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref entity-service)}"
export LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE="${LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref circle-service)}"
export LOCAL_GAMMA_RTC_SERVICE_IMAGE="${LOCAL_GAMMA_RTC_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref rtc-service)}"

skip_build=0
skip_up=0
print_env=0
down=0
tunnel_pid_file="${LOCAL_GAMMA_STATE_ROOT}/colima-tunnels.pids"
media_origin_pid_file="${LOCAL_GAMMA_STATE_ROOT}/media-origin.pid"
stack_report="${LOCAL_GAMMA_STACK_REPORT}"
gamma_proxy_ensure_attempts=0

# wait_local_gamma_host_ready() 会在 podman/manual 与 docker compose 两条路径共用。
# docker compose 分支会在后面重载成真实探测逻辑；这里提供默认 noop，
# 避免 podman/manual 路径命中“command not found”。
ensure_docker_gamma_proxy_started() {
  return 0
}

local_gamma_has_existing_stack() {
  if docker compose -f "$COMPOSE_FILE" ps -q 2>/dev/null | awk 'NF {found=1} END {exit found ? 0 : 1}'; then
    return 0
  fi
  if command -v podman >/dev/null 2>&1 && \
    podman ps -a --format '{{.Names}}' 2>/dev/null | awk '/^quwoquan_service_(gamma-proxy|assistant-service|user-service|chat-service|content-service|product-ops-service|tag-service|search-service|entity-service|circle-service|rec-model-service|elasticsearch|redis|mongodb|postgres)_1$/ {found=1} END {exit found ? 0 : 1}'; then
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

list_listening_pids_for_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null \
      | awk -v port=":${port}" '$4 ~ port {print}' \
      | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p'
  fi
}

stop_media_origin() {
  local port="${LOCAL_GAMMA_MEDIA_ORIGIN_PORT}"
  local pid=""
  local extra_pid=""
  local seen=" "
  local -a pids=()
  if [[ -f "$media_origin_pid_file" ]]; then
    pid="$(cat "$media_origin_pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
      pids+=("$pid")
      seen+=" $pid "
    fi
  fi
  while IFS= read -r extra_pid; do
    [[ -n "$extra_pid" ]] || continue
    if [[ "$seen" == *" $extra_pid "* ]]; then
      continue
    fi
    pids+=("$extra_pid")
    seen+=" $extra_pid "
  done < <(list_listening_pids_for_port "$port")
  if ((${#pids[@]} == 0)); then
    rm -f "$media_origin_pid_file"
    return 0
  fi
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      continue
    fi
    kill "$pid" >/dev/null 2>&1 || true
    local deadline=$((SECONDS + 10))
    while kill -0 "$pid" >/dev/null 2>&1; do
      if (( SECONDS >= deadline )); then
        kill -9 "$pid" >/dev/null 2>&1 || true
        break
      fi
      sleep 0.2
    done
  done
  rm -f "$media_origin_pid_file"
}

cleanup_existing_gamma_runtime() {
  local base_name=""
  local container_name=""
  local image_name=""
  local -a base_names=(
    gamma-proxy
    assistant-service
    user-service
    chat-service
    content-service
    product-ops-service
    tag-service
    search-service
    entity-service
    circle-service
    mongo-init
    rec-model-service
    elasticsearch
    redis
    mongodb
    postgres
  )
  for base_name in "${base_names[@]}"; do
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
      quwoquan_service_tag-service \
      quwoquan_service_search-service \
      quwoquan_service_rec-model-service \
      quwoquan_service_rtc-service; do
      podman rmi -f "$image_name" >/dev/null 2>&1 || true
      podman rmi -f "localhost/${image_name}:latest" >/dev/null 2>&1 || true
    done
  fi
}

start_media_origin() {
  # 与 docker `/srv/media` 挂载同源：URL `/media/image/...` 解析为
  # Caddy `root * /srv/media` + `handle /media/*` 同源：URL `/media/image/...` 解析为
  # `<root>/media/image/...`，curated bundle 实际落在 state/local/gamma/media/media/...，
  # 故 origin 静态服务 root 必须为 state/local/gamma/media（而非其父目录）。
  # 某些远端 ECS 的 python3 过旧，不支持 `python3 -m http.server --directory ...`；
  # 这里改为内嵌 SimpleHTTPRequestHandler，避免 CLI 选项兼容性问题。
  local media_root="${LOCAL_GAMMA_MEDIA_ROOT}"
  local log_file="${LOCAL_GAMMA_STATE_ROOT}/media-origin.log"
  mkdir -p "$media_root"
  stop_media_origin
  nohup python3 - "${LOCAL_GAMMA_MEDIA_ORIGIN_PORT}" "$media_root" \
    </dev/null >"$log_file" 2>&1 <<'PY' &
import http.server
import os
import socketserver
import sys

port = int(sys.argv[1])
media_root = sys.argv[2]
os.chdir(media_root)


class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


with ReuseTCPServer(("127.0.0.1", port), http.server.SimpleHTTPRequestHandler) as httpd:
    httpd.serve_forever()
PY
  local pid="$!"
  echo "$pid" > "$media_origin_pid_file"
  python3 - "${LOCAL_GAMMA_MEDIA_ORIGIN_PORT}" <<'PY'
import sys
import time
import urllib.request

port = int(sys.argv[1])
deadline = time.time() + 30
last = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
            timeout=2,
        ) as resp:
            if 200 <= int(resp.status) < 300:
                resp.read()
                raise SystemExit(0)
            last = f"http {resp.status}"
    except Exception as exc:  # noqa: BLE001
        last = str(exc)
    time.sleep(0.5)
raise SystemExit(last or "media origin not ready")
PY
}

host_port_open() {
  local port="$1"
  python3 - "$port" <<'PY'
import sys
import urllib.request

port = sys.argv[1]
try:
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2).read()
except Exception:
    raise SystemExit(1)
if b"business-beta" in body.lower():
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
  local ssh_config="${LOCAL_GAMMA_STATE_ROOT}/colima-ssh-config"
  mkdir -p "${LOCAL_GAMMA_STATE_ROOT}" "${LOCAL_GAMMA_MODEL_CACHE_ROOT}"
  stop_colima_tunnels
  colima ssh-config > "$ssh_config"
  : > "$tunnel_pid_file"
  for port in "$http_port" "$product_ops_port" "$media_edge_port" "$user_port"; do
    if host_port_open "$port"; then
      continue
    fi
    ssh -F "$ssh_config" -N -L "127.0.0.1:${port}:127.0.0.1:${port}" colima \
      > "${LOCAL_GAMMA_STATE_ROOT}/colima-tunnel-${port}.log" 2>&1 &
    echo "$!" >> "$tunnel_pid_file"
  done
  sleep 2
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
  rm -rf "$out"
  mkdir -p \
    "$out/configs/content-service/default" \
    "$out/configs/content-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/content-service" \
    "$out/configs/chat-service/default" \
    "$out/configs/chat-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/chat-service" \
    "$out/configs/user-service/default" \
    "$out/configs/user-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/user-service" \
    "$out/configs/assistant-service/default" \
    "$out/configs/assistant-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/assistant-service" \
    "$out/deploy/shared" \
    "$out/configs/product-ops-service/default" \
    "$out/configs/product-ops-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/product-ops-service" \
    "$out/configs/recommendation-service/default" \
    "$out/configs/recommendation-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/recommendation-service" \
    "$out/configs/tag-service/default" \
    "$out/configs/tag-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/tag-service" \
    "$out/configs/search-service/default" \
    "$out/configs/search-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/search-service" \
    "$out/configs/entity-service/default" \
    "$out/configs/entity-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/entity-service" \
    "$out/configs/circle-service/default" \
    "$out/configs/circle-service/${CONFIG_SOURCE_ENV}" \
    "$out/releases/config/circle-service"
  cp "$ROOT/quwoquan_service/services/content-service/configs/default/config.yaml" "$out/configs/content-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/content-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/content-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/chat-service/configs/default/config.yaml" "$out/configs/chat-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/chat-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/chat-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/user-service/configs/default/config.yaml" "$out/configs/user-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/user-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/user-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/assistant-service/configs/default/config.yaml" "$out/configs/assistant-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/assistant-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/assistant-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/deploy/shared/reliable_task_module_catalog.yaml" "$out/deploy/shared/reliable_task_module_catalog.yaml"
  cp "$ROOT/deploy/shared/reliable_task_retention_policy.yaml" "$out/deploy/shared/reliable_task_retention_policy.yaml"
  cp "$ROOT/quwoquan_service/services/product-ops-service/configs/default/config.yaml" "$out/configs/product-ops-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/product-ops-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/product-ops-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/rec-model-service/configs/default/config.yaml" "$out/configs/recommendation-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/rec-model-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/recommendation-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/tag-service/configs/default/config.yaml" "$out/configs/tag-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/tag-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/tag-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/search-service/configs/default/config.yaml" "$out/configs/search-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/search-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/search-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/entity-service/configs/default/config.yaml" "$out/configs/entity-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/entity-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/entity-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/circle-service/configs/default/config.yaml" "$out/configs/circle-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/circle-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/circle-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cat > "$out/releases/config/content-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/chat-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/user-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/assistant-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/product-ops-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/recommendation-service/${CONFIG_VERSION}.yaml" <<YAML
config:
  version: "${CONFIG_VERSION}"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"
service:
  http:
    addr: ":8000"
YAML
  cat > "$out/releases/config/tag-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/search-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/entity-service/${CONFIG_VERSION}.yaml" <<YAML
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
  cat > "$out/releases/config/circle-service/${CONFIG_VERSION}.yaml" <<YAML
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
}

prepare_media_root() {
  local media="${LOCAL_GAMMA_MEDIA_ROOT}"
  local canonical_media_root="$ROOT/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
  local required_sample="$media/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
  if [[ -d "$media/media" ]]; then
    if [[ -f "$required_sample" ]]; then
      echo "[local-gamma] reuse pre-synced gamma curated media bundle: $media"
      return 0
    fi
    echo "[local-gamma] gamma media root exists but key sample is missing; rebuilding bundle: $required_sample" >&2
    rm -rf "$media"
  fi
  if [[ "$ENABLE_FIXTURE_SEEDS" != "1" ]]; then
    echo "[local-gamma] FAIL: STAGE=${STAGE} requires an existing media root at ${media}/media" >&2
    return 1
  fi
  if [[ -d "$canonical_media_root" ]]; then
    python3 "$ROOT/quwoquan_service/scripts/seed/build_gamma_curated_fixture_bundle.py" \
      --output-media-root "$media" >/dev/null
    return 0
  fi
  echo "[local-gamma] FAIL: curated gamma media bundle is unavailable; sync state/local/gamma/media first" >&2
  return 1
}

prepare_caddyfile() {
  local out="${LOCAL_GAMMA_CADDYFILE}"
  mkdir -p "$(dirname "$out")"
  python3 - "$out" "$MEDIA_ORIGIN_BASE_URL" <<'PY'
import sys
from pathlib import Path

out_path = Path(sys.argv[1])
media_origin = sys.argv[2].strip().rstrip("/")
# 容器内 reverse_proxy 到 127.0.0.1/localhost 会命中容器自身 loopback。
# local-gamma 默认应直接服务挂载的 curated media bundle，仅在显式传入可达公网/宿主地址时才回源。
if media_origin.startswith(("http://127.0.0.1", "https://127.0.0.1", "http://localhost", "https://localhost")):
    media_origin = ""

if media_origin:
    media_api_block = "\n".join(
        [
            "\thandle /media/* {",
            "\t\timport media_cors",
            f"\t\treverse_proxy {media_origin}",
            "\t}",
        ]
    )
    media_host_block = "\n".join(
        [
            "gamma-avatar.quwoquan-env.test,",
            "gamma-image.quwoquan-env.test,",
            "gamma-video.quwoquan-env.test,",
            "gamma-upload.quwoquan-env.test {",
            "\timport local_gamma_tls",
            "\timport media_cors",
            f"\treverse_proxy {media_origin}",
            "}",
        ]
    )
    media_pub_block = "\n".join(
        [
            "\thandle /media/* {",
            "\t\timport media_cors",
            f"\t\treverse_proxy {media_origin}",
            "\t}",
        ]
    )
else:
    media_api_block = "\n".join(
        [
            "\thandle /media/* {",
            "\t\timport media_cors",
            "\t\troot * /srv/media",
            "\t\tfile_server",
            "\t}",
        ]
    )
    media_host_block = "\n".join(
        [
            "gamma-avatar.quwoquan-env.test,",
            "gamma-image.quwoquan-env.test,",
            "gamma-video.quwoquan-env.test,",
            "gamma-upload.quwoquan-env.test {",
            "\timport local_gamma_tls",
            "\timport media_cors",
            "\troot * /srv/media",
            "\tfile_server",
            "}",
        ]
    )
    media_pub_block = "\n".join(
        [
            "\thandle /media/* {",
            "\t\timport media_cors",
            "\t\troot * /srv/media",
            "\t\tfile_server",
            "\t}",
        ]
    )

content = f"""{{ 
\tadmin 0.0.0.0:2019
\tlocal_certs
}}

(local_gamma_tls) {{
\ttls internal
}}

(media_cors) {{
\theader {{
\t\tAccess-Control-Allow-Origin "*"
\t\tAccess-Control-Allow-Methods "GET, HEAD, OPTIONS"
\t\tAccess-Control-Allow-Headers "*"
\t\tCross-Origin-Resource-Policy "cross-origin"
\t}}
}}

gamma-api.quwoquan-env.test {{
\timport local_gamma_tls
\thandle /healthz {{
\t\treverse_proxy content-service:18080
\t}}
\thandle /v1/config/app {{
\t\treverse_proxy content-service:18080
\t}}
\thandle /livez {{
\t\treverse_proxy content-service:18080
\t}}
\thandle /startupz {{
\t\treverse_proxy content-service:18080
\t}}
\t@api_content path /v1/content*
\thandle @api_content {{
\t\treverse_proxy content-service:18080
\t}}
\t@api_chat path /v1/chat*
\thandle @api_chat {{
\t\treverse_proxy chat-service:18081
\t}}
\t@api_user path /v1/user* /v1/me /v1/me/*
\thandle @api_user {{
\t\treverse_proxy user-service:18082
\t}}
\t@api_assistant path /v1/assistant*
\thandle @api_assistant {{
\t\treverse_proxy assistant-service:18087
\t}}
\t@api_tag path /v1/tag*
\thandle @api_tag {{
\t\treverse_proxy tag-service:18092
\t}}
\t@api_search path /v1/search*
\thandle @api_search {{
\t\treverse_proxy search-service:18095
\t}}
\t@api_entity path /v1/homepages*
\thandle @api_entity {{
\t\treverse_proxy entity-service:18084
\t}}
\t@api_circle path /v1/circles*
\thandle @api_circle {{
\t\treverse_proxy circle-service:18082
\t}}
\thandle /v1/ops/* {{
\t\treverse_proxy product-ops-service:18086
\t}}
{media_api_block}
\thandle {{
\t\trespond "local-gamma mirror route is not ready for this path" 404
\t}}
}}

gamma-product-ops.quwoquan-env.test {{
\timport local_gamma_tls
\thandle /healthz {{
\t\treverse_proxy product-ops-service:18086
\t}}
\thandle /v1/ops/* {{
\t\treverse_proxy product-ops-service:18086
\t}}
\thandle {{
\t\trespond "local-gamma product-ops route is not ready for this path" 404
\t}}
}}

{media_host_block}

:80 {{
\thandle /healthz {{
\t\treverse_proxy content-service:18080
\t}}
\thandle /v1/config/app {{
\t\treverse_proxy content-service:18080
\t}}
\t@pub_content path /v1/content*
\thandle @pub_content {{
\t\treverse_proxy content-service:18080
\t}}
\t@pub_chat path /v1/chat*
\thandle @pub_chat {{
\t\treverse_proxy chat-service:18081
\t}}
\t@pub_user path /v1/user* /v1/me /v1/me/*
\thandle @pub_user {{
\t\treverse_proxy user-service:18082
\t}}
\t@pub_assistant path /v1/assistant*
\thandle @pub_assistant {{
\t\treverse_proxy assistant-service:18087
\t}}
\t@pub_tag path /v1/tag*
\thandle @pub_tag {{
\t\treverse_proxy tag-service:18092
\t}}
\t@pub_search path /v1/search*
\thandle @pub_search {{
\t\treverse_proxy search-service:18095
\t}}
\t@pub_entity path /v1/homepages*
\thandle @pub_entity {{
\t\treverse_proxy entity-service:18084
\t}}
\t@pub_circle path /v1/circles*
\thandle @pub_circle {{
\t\treverse_proxy circle-service:18082
\t}}
\thandle /v1/ops/* {{
\t\treverse_proxy product-ops-service:18086
\t}}
{media_pub_block}
\thandle {{
\t\trespond "local-gamma mirror route is not ready for this path" 404
\t}}
}}
"""
out_path.write_text(content.replace("{ ", "{").replace("\n\n\n", "\n\n"), encoding="utf-8")
PY
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
    --media-base-url "$MEDIA_BASE_URL"
}

preflight_local_gamma_inputs() {
  if [[ ! -d "$LOCAL_GAMMA_TAGS_DIR" ]]; then
    bootstrap_local_gamma_tag_taxonomy || return 1
  fi
  if [[ ! -f "$LOCAL_GAMMA_TAG_OBJECTS_FILE" ]]; then
    echo "[local-gamma] FAIL: missing object_tag_index fixture: $LOCAL_GAMMA_TAG_OBJECTS_FILE" >&2
    return 1
  fi
}

bootstrap_local_gamma_tag_taxonomy() {
  local publish_root="${LOCAL_GAMMA_TAGS_DIR%/tags}"
  if [[ "$publish_root" == "$LOCAL_GAMMA_TAGS_DIR" ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_TAGS_DIR must end with /tags: $LOCAL_GAMMA_TAGS_DIR" >&2
    return 1
  fi
  echo "[local-gamma] tag taxonomy missing; bootstrapping current source of truth into $LOCAL_GAMMA_TAGS_DIR" >&2
  mkdir -p "$publish_root"
  env QWQ_PUBLISH_ROOT="$publish_root" \
    python3 "$ROOT/quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_tags.py"
  env QWQ_PUBLISH_ROOT="$publish_root" \
    python3 "$ROOT/quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_admin_regions.py"
  env QWQ_PUBLISH_ROOT="$publish_root" \
    python3 "$ROOT/quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_geo_landmarks.py"
  env QWQ_PUBLISH_ROOT="$publish_root" \
    python3 "$ROOT/quwoquan_data/scripts/verify/verify_tag_tree.py"
  env QWQ_PUBLISH_ROOT="$publish_root" \
    python3 "$ROOT/quwoquan_data/scripts/publish_ops/build_publish_lookup_indexes.py"
  if [[ ! -d "$LOCAL_GAMMA_TAGS_DIR" ]]; then
    echo "[local-gamma] FAIL: tag taxonomy bootstrap finished without creating $LOCAL_GAMMA_TAGS_DIR" >&2
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
  local build_log="${LOCAL_GAMMA_STATE_ROOT}/docker-build.log"
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

if [[ "$down" == "1" ]]; then
  stop_colima_tunnels
  stop_media_origin
  docker compose -f "$COMPOSE_FILE" down
  rm -f "$stack_report"
  exit 0
fi

prepare_config_root
prepare_media_root
mkdir -p "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" "${LOCAL_GAMMA_ARTIFACT_ROOT}"
start_media_origin
prepare_caddyfile

if [[ "$print_env" == "1" ]]; then
  print_defines
fi

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
  compose_cmd=(docker compose -f "$COMPOSE_FILE")
  compose_up_args=(up -d --remove-orphans --force-recreate)
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
  tag-service
  search-service
  entity-service
  circle-service
)
if [[ ",${COMPOSE_PROFILES:-}," == *,edge-media,* ]]; then
  compose_build_services+=(rtc-service)
fi

if [[ "$FORCE_CLEAN_RECREATE" == "1" ]]; then
  echo "[local-gamma] forcing clean recreate of existing gamma containers"
  cleanup_existing_gamma_runtime
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
    quwoquan_service_tag-service_1 \
    quwoquan_service_search-service_1 \
    quwoquan_service_entity-service_1 \
    quwoquan_service_circle-service_1 \
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
  podman volume inspect quwoquan_service_local-gamma-caddy-data >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-caddy-data >/dev/null
  podman volume inspect quwoquan_service_local-gamma-caddy-config >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-caddy-config >/dev/null
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
    -e PRODUCT_OPS_REDIS_REC_ADDR=redis:6379 -e PRODUCT_OPS_REDIS_GENERAL_ADDR=redis:6379 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}:18086" \
    -p "${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}:18086" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18086/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_product-ops-service_1

  podman run --pull=never --name quwoquan_service_content-service_1 -d \
    --net "$network_name" --network-alias content-service \
    -e SERVICE_NAME=content-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e MONGO_URI=mongodb://mongodb:27017 \
    -e CONTENT_REDIS_REC_ADDR=redis:6379 -e CONTENT_REDIS_GENERAL_ADDR=redis:6379 \
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
    -v quwoquan_service_local-gamma-caddy-data:/data \
    -v quwoquan_service_local-gamma-caddy-config:/config \
    -p "${LOCAL_GAMMA_HTTP_PORT:-19000}:80" \
    -p "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}:80" \
    -p "${LOCAL_GAMMA_HTTPS_PORT:-443}:443" \
    -p "${LOCAL_GAMMA_ADMIN_PORT:-2019}:2019" \
    --healthcheck-command "wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 5s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CADDY_IMAGE" >/dev/null
  wait_healthy quwoquan_service_gamma-proxy_1
else
  echo "[local-gamma] startup mode: compose-up"
  # Recreate the local mirror on every gate run so changed host port envs take effect.
  "${compose_cmd[@]}" down --remove-orphans >/dev/null 2>&1 || true
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
  compose_up_failed=0
  if ! "${compose_cmd[@]}" "${compose_up_args[@]}"; then
    # Docker compose may return early while health checks are still converging.
    # Keep the existing readiness probes as the final source of truth.
    compose_up_failed=1
    echo "[local-gamma] WARN: compose up reported a startup error; deferring to host readiness probes" >&2
  fi
  ensure_docker_gamma_proxy_started || true
fi
start_colima_tunnels_if_needed

# docker compose 分支不会逐项 wait_healthy；在宣告就绪前用主机侧探测避免 T3/T4 撞到端口未监听。
wait_local_gamma_host_ready() {
  local gw="${GATEWAY_BASE_URL%/}"
  local gw_local="http://127.0.0.1:${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local media_edge_local="http://127.0.0.1:${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  local po_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local deadline=$(( $(date +%s) + HOST_READY_TIMEOUT_SECONDS ))
  local last_gamma_proxy_retry=0
  echo "[local-gamma] waiting for host probes (${HOST_READY_TIMEOUT_SECONDS}s): ${gw}/healthz or ${gw_local}/healthz + ${media_edge_local}/healthz + http://127.0.0.1:${po_port}/healthz + http://127.0.0.1:${user_port}/healthz"
  while (( $(date +%s) < deadline )); do
    if (( $(date +%s) - last_gamma_proxy_retry >= 15 )); then
      ensure_docker_gamma_proxy_started || true
      last_gamma_proxy_retry=$(date +%s)
    fi
    if python3 - <<PY
import urllib.request
gateway_urls = ["${gw}/healthz"]
if "${gw_local}/healthz" not in gateway_urls:
    gateway_urls.append("${gw_local}/healthz")
if "${media_edge_local}/healthz" not in gateway_urls:
    gateway_urls.append("${media_edge_local}/healthz")
gateway_ready = False
for url in gateway_urls:
    try:
        body = urllib.request.urlopen(url, timeout=4).read()
    except Exception:
        continue
    if b"business-beta" in body.lower():
        continue
    gateway_ready = True
    break
if not gateway_ready:
    raise SystemExit(1)
for url in ("http://127.0.0.1:${po_port}/healthz", "http://127.0.0.1:${user_port}/healthz"):
    try:
        body = urllib.request.urlopen(url, timeout=4).read()
    except Exception:
        raise SystemExit(1)
    if b"business-beta" in body.lower():
        raise SystemExit(1)
raise SystemExit(0)
PY
    then
      return 0
    fi
    sleep 2
  done
  echo "[local-gamma] FAIL: host cannot reach ${gw}/healthz or ${gw_local}/healthz plus ${media_edge_local}/healthz and http://127.0.0.1:${po_port}/healthz within ${HOST_READY_TIMEOUT_SECONDS}s" >&2
  python3 - <<PY >&2
import urllib.request

urls = [
    "${gw}/healthz",
    "${gw_local}/healthz",
    "${media_edge_local}/healthz",
    "http://127.0.0.1:${po_port}/healthz",
    "http://127.0.0.1:${user_port}/healthz",
]
for url in urls:
    try:
        body = urllib.request.urlopen(url, timeout=4).read(120)
        print(f"[local-gamma] probe {url} -> ok body={body!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[local-gamma] probe {url} -> {exc}")
PY
  docker compose -f "$COMPOSE_FILE" ps >&2 || true
  docker compose -f "$COMPOSE_FILE" logs --tail 80 gamma-proxy product-ops-service user-service >&2 || true
  return 1
}
wait_local_gamma_host_ready

if [[ "${compose_up_failed:-0}" == "1" ]]; then
  echo "[local-gamma] WARN: host probes recovered after compose startup reported an error" >&2
fi

# tag-service 数据在 local-gamma 启动时按当前真相源重建：
#  - tag_nodes ← publish/tags（路径制 taxonomy，唯一标签真相源）
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
    echo "[local-gamma] WARN: skip content seed because python3 < 3.10 on this host" >&2
    return 0
  fi
  if ! python3 "$ROOT/quwoquan_app/scripts/gamma/run_local_gamma_t3.py" --seed-only --report "${LOCAL_GAMMA_ARTIFACT_ROOT}/content-seed-report.json"; then
    echo "[local-gamma] WARN: content seed failed; home/discovery feeds may be empty until seed succeeds" >&2
    return 0
  fi
  echo "[local-gamma] content seed completed"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_gamma_content_data
else
  echo "[local-gamma] skip content seed because STAGE=${STAGE} uses persisted/host data"
fi

# search-service 的 ES 召回读模型 cold-start：把已 seed 的内容（quwoquan_content.posts）
# 经统一投影回填进共享 ES 索引 quwoquan_objects（与 search-service 查询同一索引）。
# 这是检索读模型的环境 seed，与 tag/content seed 同级，保证 /v1/search 返回真实 hit。
seed_search_index() {
  local es_port="${LOCAL_GAMMA_ES_PORT:-}"
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  if [[ -z "$es_port" || -z "$mongo_port" ]]; then
    echo "[local-gamma] WARN: skip search backfill; LOCAL_GAMMA_ES_PORT/MONGO_PORT unset" >&2
    return 0
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
    echo "[local-gamma] WARN: ES host port ${es_port} not ready; search index left empty" >&2
    return 0
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
      --posts-db quwoquan_content --env gamma --batch-size 100 ); then
    echo "[local-gamma] WARN: search backfill failed; /v1/search will return empty hits until indexed" >&2
    return 0
  fi
  echo "[local-gamma] search index backfill completed"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_search_index
else
  echo "[local-gamma] skip search backfill because STAGE=${STAGE} uses persisted/host data"
fi

python3 - "$stack_report" "$CONFIG_VERSION" "$IMAGE_VERSION" "$PREVIOUS_IMAGE_VERSION" "$STAGE" "$LOCAL_GAMMA_APP_ENV" "$CONFIG_SOURCE_ENV" "$GATEWAY_BASE_URL" "$PRODUCT_OPS_BASE_URL" "$MEDIA_BASE_URL" "$LOCAL_MEDIA_ORIGIN_URL" "$restarted_from_previous" <<'PY'
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
    media_origin,
    restarted,
) = sys.argv[1:13]
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
    "mediaOriginBaseUrl": media_origin,
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
echo "[local-gamma] media-origin: $LOCAL_MEDIA_ORIGIN_URL"
echo "[local-gamma] dart defines:"
print_defines
