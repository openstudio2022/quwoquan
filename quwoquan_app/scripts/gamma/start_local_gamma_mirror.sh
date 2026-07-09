#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
COMPOSE_FILE="$ROOT/quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
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
  eval "$(python3 "$ROOT/quwoquan_ops/cli/print_local_port_profile.py" --profile gamma-local --format shell-defaults)"
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
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-https://gamma-api.quwoquan-env.test:${LOCAL_GAMMA_HTTP_PORT}}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-https://gamma-product-ops.quwoquan-env.test:${LOCAL_GAMMA_PRODUCT_OPS_PORT}}"
MEDIA_BASE_URL="${LOCAL_GAMMA_MEDIA_PUBLIC_BASE_URL:-${LOCAL_GAMMA_MEDIA_BASE_URL:-https://gamma-image.quwoquan-env.test:${LOCAL_GAMMA_MEDIA_EDGE_PORT}}}"
MEDIA_ORIGIN_BASE_URL="${LOCAL_GAMMA_MEDIA_ORIGIN_BASE_URL:-}"
LOCAL_MEDIA_ORIGIN_URL="http://127.0.0.1:${LOCAL_GAMMA_MEDIA_ORIGIN_PORT}"
PUBLIC_HOSTS=(
  gamma-api.quwoquan-env.test
  gamma-product-ops.quwoquan-env.test
  gamma-avatar.quwoquan-env.test
  gamma-image.quwoquan-env.test
  gamma-video.quwoquan-env.test
  gamma-upload.quwoquan-env.test
)
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
LOCAL_GAMMA_LOCAL_ROOT="${LOCAL_GAMMA_LOCAL_ROOT:-$ROOT/.qwq_output/local/gamma-local}"
LOCAL_GAMMA_ARTIFACT_ROOT="${LOCAL_GAMMA_ARTIFACT_ROOT:-${LOCAL_GAMMA_LOCAL_ROOT}/app-artifacts}"
LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_LOCAL_ROOT}/config-root"
LOCAL_GAMMA_MEDIA_ROOT="${LOCAL_GAMMA_LOCAL_ROOT}/media"
LOCAL_GAMMA_CADDYFILE="${LOCAL_GAMMA_LOCAL_ROOT}/Caddyfile"
LOCAL_GAMMA_CADDY_DATA_ROOT="${LOCAL_GAMMA_CADDY_DATA_ROOT:-${LOCAL_GAMMA_LOCAL_ROOT}/caddy/data}"
LOCAL_GAMMA_CADDY_CONFIG_ROOT="${LOCAL_GAMMA_CADDY_CONFIG_ROOT:-${LOCAL_GAMMA_LOCAL_ROOT}/caddy/config}"
LOCAL_GAMMA_MODEL_CACHE_ROOT="${LOCAL_GAMMA_LOCAL_ROOT}/model-cache"
LOCAL_GAMMA_STACK_STATUS_REPORT="${LOCAL_GAMMA_LOCAL_ROOT}/stack_status.json"
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
LOCAL_GAMMA_LEGAL_STATIC_ROOT="${LOCAL_GAMMA_LEGAL_STATIC_ROOT:-$ROOT/.qwq_output/release/legal-static/${CONFIG_SOURCE_ENV}/current/public}"
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
  LOCAL_GAMMA_CADDY_DATA_ROOT \
  LOCAL_GAMMA_CADDY_CONFIG_ROOT \
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
tunnel_pid_file="${LOCAL_GAMMA_LOCAL_ROOT}/colima-tunnels.pids"
media_origin_pid_file="${LOCAL_GAMMA_LOCAL_ROOT}/media-origin.pid"
stack_report="${LOCAL_GAMMA_STACK_STATUS_REPORT}"
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
  # `<root>/media/image/...`，curated bundle 实际落在 .qwq_output/local/gamma-local/media/media/...，
  # 故 origin 静态服务 root 必须为 .qwq_output/local/gamma-local/media（而非其父目录）。
  # 远端 gamma 已退役、仅保留 gamma-local（本机现代 python3），复用 alpha/prod-sim
  # 同一份支持 HTTP Range(206) 的 origin（quwoquan_ops/cli/lib/local_media_origin.py），
  # 避免内嵌 SimpleHTTPRequestHandler 忽略 Range 导致 iOS AVPlayer 卡在加载/无法播放，
  # 同时不再维护第二份 origin 实现。gamma-local 用真实 curated 资产，无需会话头像 alias。
  local media_root="${LOCAL_GAMMA_MEDIA_ROOT}"
  local log_file="${LOCAL_GAMMA_LOCAL_ROOT}/media-origin.log"
  mkdir -p "$media_root"
  stop_media_origin
  nohup python3 "$ROOT/quwoquan_ops/cli/lib/local_media_origin.py" \
    --listen-host 127.0.0.1 \
    --listen-port "${LOCAL_GAMMA_MEDIA_ORIGIN_PORT}" \
    --root-dir "$media_root" \
    --server-label gamma-local-media-origin \
    </dev/null >"$log_file" 2>&1 &
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
  local ssh_config="${LOCAL_GAMMA_LOCAL_ROOT}/colima-ssh-config"
  mkdir -p \
    "${LOCAL_GAMMA_LOCAL_ROOT}" \
    "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" \
    "${LOCAL_GAMMA_CADDY_DATA_ROOT}" \
    "${LOCAL_GAMMA_CADDY_CONFIG_ROOT}" \
    "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}"
  stop_colima_tunnels
  colima ssh-config > "$ssh_config"
  : > "$tunnel_pid_file"
  for port in "$http_port" "$product_ops_port" "$media_edge_port" "$user_port"; do
    if host_port_open "$port"; then
      continue
    fi
    ssh -F "$ssh_config" -N -L "127.0.0.1:${port}:127.0.0.1:${port}" colima \
      > "${LOCAL_GAMMA_LOCAL_ROOT}/colima-tunnel-${port}.log" 2>&1 &
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
    "$out/quwoquan_service/services/circle-service/configs/releases"
  cp "$ROOT/quwoquan_service/services/content-service/configs/default/config.yaml" "$out/configs/content-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/content-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/content-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/chat-service/configs/default/config.yaml" "$out/configs/chat-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/chat-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/chat-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/user-service/configs/default/config.yaml" "$out/configs/user-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/user-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/user-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_service/services/assistant-service/configs/default/config.yaml" "$out/configs/assistant-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/assistant-service/configs/${CONFIG_SOURCE_ENV}/config.yaml" "$out/configs/assistant-service/${CONFIG_SOURCE_ENV}/config.yaml"
  cp "$ROOT/quwoquan_ops/environments/reliable_task_module_catalog.yaml" "$out/quwoquan_ops/environments/reliable_task_module_catalog.yaml"
  cp "$ROOT/quwoquan_ops/environments/reliable_task_retention_policy.yaml" "$out/quwoquan_ops/environments/reliable_task_retention_policy.yaml"
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
}

prepare_media_root() {
  local media="${LOCAL_GAMMA_MEDIA_ROOT}"
  local canonical_media_root="$ROOT/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
  local required_sample="$media/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
  local required_avatar="$media/media/avatar/s/archived-avatar/circle/fixture_circle_coffee_04/v1/avatar.png"
  local required_video="$media/media/video/s/archived-video/beta-sample.mp4"
  local media_file_count=0
  if [[ -d "$media/media" ]]; then
    media_file_count="$(find "$media/media" -type f | wc -l | tr -d '[:space:]')"
    if [[ -f "$required_sample" && -f "$required_avatar" && -f "$required_video" && "$media_file_count" -ge 1000 ]]; then
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
    mkdir -p "$media"
    cp -R "$canonical_media_root/." "$media/"
    return 0
  fi
  echo "[local-gamma] FAIL: curated gamma media bundle is unavailable; sync .qwq_output/local/gamma-local/media first" >&2
  return 1
}

prepare_caddyfile() {
  local out="${LOCAL_GAMMA_CADDYFILE}"
  mkdir -p \
    "$(dirname "$out")" \
    "$LOCAL_GAMMA_CADDY_DATA_ROOT" \
    "$LOCAL_GAMMA_CADDY_CONFIG_ROOT"
  python3 - \
    "$out" \
    "$MEDIA_ORIGIN_BASE_URL" \
    "$LOCAL_GAMMA_HTTP_PORT" \
    "$LOCAL_GAMMA_PRODUCT_OPS_PORT" \
    "$LOCAL_GAMMA_MEDIA_EDGE_PORT" <<'PY'
import sys
from pathlib import Path

out_path = Path(sys.argv[1])
media_origin = sys.argv[2].strip().rstrip("/")
api_port = sys.argv[3].strip()
product_ops_port = sys.argv[4].strip()
media_edge_port = sys.argv[5].strip()
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
            "gamma-upload.quwoquan-env.test,",
            "gamma-avatar.localhost,",
            "gamma-image.localhost,",
            "gamma-video.localhost,",
            "gamma-upload.localhost {",
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
            "gamma-upload.quwoquan-env.test,",
            "gamma-avatar.localhost,",
            "gamma-image.localhost,",
            "gamma-video.localhost,",
            "gamma-upload.localhost {",
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
legal_static_block = "\n".join(
    [
        "\thandle /legal/* {",
        "\t\theader {",
        '\t\t\tCache-Control "public, max-age=300"',
        '\t\t\tX-Content-Type-Options "nosniff"',
        "\t\t}",
        "\t\troot * /srv/legal",
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

gamma-api.quwoquan-env.test,
gamma-api.localhost {{
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
{legal_static_block}
{media_api_block}
\thandle {{
\t\trespond "local-gamma mirror route is not ready for this path" 404
\t}}
}}

gamma-product-ops.quwoquan-env.test,
gamma-product-ops.localhost {{
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
{legal_static_block}
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
  local build_log="${LOCAL_GAMMA_LOCAL_ROOT}/docker-build.log"
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
mkdir -p "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" "${LOCAL_GAMMA_ARTIFACT_ROOT}" "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}"
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
    -v "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}:/srv/legal:ro" \
    -v "${LOCAL_GAMMA_CADDY_DATA_ROOT}:/data" \
    -v "${LOCAL_GAMMA_CADDY_CONFIG_ROOT}:/config" \
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
ensure_public_hosts_mapping

# docker compose 分支不会逐项 wait_healthy；在宣告就绪前用主机侧探测避免 T3/T4 撞到端口未监听。
wait_local_gamma_host_ready() {
  local gw="${GATEWAY_BASE_URL%/}"
  local gw_host="gamma-api.quwoquan-env.test"
  local gw_port="${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local product_ops_host="gamma-product-ops.quwoquan-env.test"
  local product_ops_public_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local media_host="gamma-image.quwoquan-env.test"
  local media_edge_port="${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  local po_port="${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}"
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local deadline=$(( $(date +%s) + HOST_READY_TIMEOUT_SECONDS ))
  local last_gamma_proxy_retry=0
  echo "[local-gamma] waiting for host probes (${HOST_READY_TIMEOUT_SECONDS}s): ${gw}/healthz + ${PRODUCT_OPS_BASE_URL%/}/healthz + ${MEDIA_BASE_URL%/}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png + http://127.0.0.1:${po_port}/healthz + http://127.0.0.1:${user_port}/healthz"
  while (( $(date +%s) < deadline )); do
    if (( $(date +%s) - last_gamma_proxy_retry >= 15 )); then
      ensure_docker_gamma_proxy_started || true
      last_gamma_proxy_retry=$(date +%s)
    fi
    if curl -kfsS --resolve "${gw_host}:${gw_port}:127.0.0.1" "https://${gw_host}:${gw_port}/healthz" >/dev/null 2>&1 \
      && curl -kfsS --resolve "${product_ops_host}:${product_ops_public_port}:127.0.0.1" "https://${product_ops_host}:${product_ops_public_port}/healthz" >/dev/null 2>&1 \
      && curl -kfsS --resolve "${media_host}:${media_edge_port}:127.0.0.1" "https://${media_host}:${media_edge_port}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${po_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${user_port}/healthz" >/dev/null 2>&1
    then
      return 0
    fi
    sleep 2
  done
  echo "[local-gamma] FAIL: host cannot reach ${gw}/healthz, ${PRODUCT_OPS_BASE_URL%/}/healthz, ${MEDIA_BASE_URL%/}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png and internal health probes within ${HOST_READY_TIMEOUT_SECONDS}s" >&2
  curl -kfsS --resolve "${gw_host}:${gw_port}:127.0.0.1" "https://${gw_host}:${gw_port}/healthz" >&2 || true
  curl -kfsS --resolve "${product_ops_host}:${product_ops_public_port}:127.0.0.1" "https://${product_ops_host}:${product_ops_public_port}/healthz" >&2 || true
  curl -kfsS --resolve "${media_host}:${media_edge_port}:127.0.0.1" "https://${media_host}:${media_edge_port}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" >&2 || true
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

seed_gamma_intersection_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local gateway="${GATEWAY_BASE_URL%/}"
  local report="${LOCAL_GAMMA_ARTIFACT_ROOT}/intersection-seed-report.json"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] WARN: skip intersection seed; LOCAL_GAMMA_MONGO_PORT unset" >&2
    return 0
  fi
  echo "[local-gamma] seeding intersection viewer relationships and read model ..."
  if ! python3 - "$mongo_port" "$gateway" "$report" <<'PY'
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

mongo_port, gateway, report_path = sys.argv[1:4]
viewer = "fixture_user_current"
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
  {{postId: profilePost, id: profilePost, authorId: person, status: 'published', authorDisplayNameSnapshot: '交集约伴体验号', authorAvatarUrlSnapshot: avatar, updatedAt: now, publishedAt: now}},
  {{postId: sharedPost, id: sharedPost, authorId: person, status: 'published', title: '交集真实证据共享内容', contentType: 'article', authorDisplayNameSnapshot: '交集约伴体验号', authorAvatarUrlSnapshot: avatar, updatedAt: now, publishedAt: now}}
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

headers = {
    "X-Client-User-Id": viewer,
    "X-Client-Session-Id": "local_gamma_intersection_seed",
}
parsed_gateway = urlparse(gateway)
gateway_host = parsed_gateway.hostname or "gamma-api.quwoquan-env.test"
gateway_port = parsed_gateway.port or (443 if parsed_gateway.scheme == "https" else 80)

def curl_json(path: str) -> dict:
    command = [
        "curl",
        "-kfsS",
        "--resolve",
        f"{gateway_host}:{gateway_port}:127.0.0.1",
    ]
    for key, value in headers.items():
        command.extend(["-H", f"{key}: {value}"])
    command.append(f"{gateway}{path}")
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"probe failed {path}: exit={result.returncode} stderr={result.stderr.strip()}"
        )
    return json.loads(result.stdout)

object_body = curl_json(
    f"/v1/content/intersections/object?objectId={person}&objectType=user&limit=8"
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

summary = curl_json("/v1/content/intersections/summary")
listing = curl_json("/v1/content/intersections?limit=8")
if int(summary.get("totalCount") or 0) <= 0:
    raise SystemExit(f"intersection summary remains empty: {summary}")
if len(listing.get("items") or []) <= 0:
    raise SystemExit(f"intersection list remains empty: {listing}")

report = {
    "viewerId": viewer,
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
    echo "[local-gamma] WARN: intersection seed failed; /v1/content/intersections may stay sparse" >&2
    return 0
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
  local report="${LOCAL_GAMMA_ARTIFACT_ROOT}/premium-pool-seed-report.json"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] WARN: skip premium pool seed; LOCAL_GAMMA_MONGO_PORT unset" >&2
    return 0
  fi
  echo "[local-gamma] seeding premium pool projection and recall proof ..."
  if ! python3 - "$mongo_port" "$gateway" "$report" <<'PY'
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

mongo_port, gateway, report_path = sys.argv[1:4]
viewer = f"fixture_user_current_premium_probe_{int(time.time())}"
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

parsed_gateway = urlparse(gateway)
gateway_host = parsed_gateway.hostname or "gamma-api.quwoquan-env.test"
gateway_port = parsed_gateway.port or (443 if parsed_gateway.scheme == "https" else 80)
command = [
    "curl",
    "-kfsS",
    "--resolve",
    f"{gateway_host}:{gateway_port}:127.0.0.1",
    "-H",
    f"X-Client-User-Id: {viewer}",
    "-H",
    "X-Client-Session-Id: local_gamma_premium_pool_seed",
    f"{gateway}/v1/content/feed?type=premium&limit=5",
]
result = subprocess.run(
    command,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if result.returncode != 0:
    raise SystemExit(
        f"premium pool probe failed: exit={result.returncode} stderr={result.stderr.strip()}"
    )
body = json.loads(result.stdout)
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
    "viewerId": viewer,
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
    echo "[local-gamma] WARN: premium pool seed failed; premium stream recall may stay unproven" >&2
    return 0
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
