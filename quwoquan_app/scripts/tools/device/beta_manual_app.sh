#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
ENTITY_SERVICE_DIR="$ROOT_DIR/quwoquan_service/services/entity-service"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
if [[ -z "${QWQ_OBSERVABILITY_RUN_ROOT:-}" || -z "${QWQ_RUN_ROOT:-}" ]]; then
  eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_run.py" \
    --env beta --target beta-local --action up --output-root "$QWQ_OUTPUT_ROOT")"
fi
export QWQ_OUTPUT_ROOT QWQ_DEPLOY_WORK_ROOT QWQ_OBSERVABILITY_RUN_ROOT QWQ_RUN_ROOT
RUNTIME_CONFIG_DIR="${QWQ_DEPLOY_WORK_ROOT}/beta-local/rendered"
CACHE_DIR="${QWQ_OUTPUT_ROOT}/env/beta/local/beta-local/cache"
LOG_DIR="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
REPORT="${QWQ_RUN_ROOT}/app-beta-manual-report.json"
BETA_LEGAL_STATIC_ROOT="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir

print(legal_static_deployment_package_dir("beta") / "current" / "public")
PY
)"
eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile beta-local --format shell-defaults)"
eval "$(PYTHONPATH="$ROOT_DIR" python3 -m quwoquan_ops.cli.lib.local_environment_auth --shell beta beta-local)"
eval "$(
  PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import shlex
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

bases = get_target(load_environment_topology(), "beta-local")["publicBases"]
for name, role in (
    ("GATEWAY_BASE_URL", "api"),
    ("LEGAL_BASE_URL", "legal"),
    ("MEDIA_AVATAR_CDN_BASE_URL", "mediaAvatar"),
    ("MEDIA_IMAGE_CDN_BASE_URL", "mediaImage"),
    ("MEDIA_VIDEO_CDN_BASE_URL", "mediaVideo"),
    ("MEDIA_UPLOAD_BASE_URL", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(bases[role]))}")
for name, role in (
    ("PUBLIC_API_HOST", "api"),
    ("PUBLIC_WEB_HOST", "publicWeb"),
    ("PUBLIC_PRODUCT_OPS_HOST", "productOps"),
    ("PUBLIC_AVATAR_HOST", "mediaAvatar"),
    ("PUBLIC_IMAGE_HOST", "mediaImage"),
    ("PUBLIC_VIDEO_HOST", "mediaVideo"),
    ("PUBLIC_UPLOAD_HOST", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(urlsplit(str(bases[role])).hostname))}")
PY
)"
CANONICAL_GATEWAY_BASE_URL="$GATEWAY_BASE_URL"
CANONICAL_LEGAL_BASE_URL="$LEGAL_BASE_URL"
CANONICAL_MEDIA_AVATAR_BASE_URL="$MEDIA_AVATAR_CDN_BASE_URL"
CANONICAL_MEDIA_IMAGE_BASE_URL="$MEDIA_IMAGE_CDN_BASE_URL"
CANONICAL_MEDIA_VIDEO_BASE_URL="$MEDIA_VIDEO_CDN_BASE_URL"
CANONICAL_MEDIA_UPLOAD_BASE_URL="$MEDIA_UPLOAD_BASE_URL"

ENTITY_PORT="${BETA_ENTITY_PORT}"
GATEWAY_PORT="${GATEWAY_PORT}"
MEDIA_PORT="${MEDIA_PORT}"
MEDIA_ORIGIN_PORT="${MEDIA_ORIGIN_PORT}"
CONTENT_PORT="${CONTENT_PORT}"
USER_PORT="${USER_PORT}"
MEDIA_PROCESSOR_PORT="${MEDIA_PROCESSOR_PORT}"
BETA_BACKING_COMPOSE_FILE="$ROOT_DIR/quwoquan_ops/environments/compose/docker-compose.beta-backing.yaml"
BETA_BACKING_COMPOSE_FILES=(
  "$BETA_BACKING_COMPOSE_FILE"
  "$ROOT_DIR/quwoquan_service/services/recommendation-service/deploy/compose.yaml"
  "$ROOT_DIR/quwoquan_service/services/content-service/deploy/compose.yaml"
  "$ROOT_DIR/quwoquan_service/services/user-service/deploy/compose.yaml"
)
BETA_BACKING_COMPOSE_ARGS=()
for beta_compose_file in "${BETA_BACKING_COMPOSE_FILES[@]}"; do
  BETA_BACKING_COMPOSE_ARGS+=(-f "$beta_compose_file")
done

BETA_BACKING_COMPOSE_PROJECT_NAME="${BETA_BACKING_COMPOSE_PROJECT_NAME:-quwoquan-beta-backing}"
BETA_POSTGRES_PORT="${BETA_POSTGRES_PORT}"
BETA_MONGO_PORT="${BETA_MONGO_PORT}"
BETA_REDIS_PORT="${BETA_REDIS_PORT}"
BETA_OBJECT_STORAGE_EDGE_PORT="${BETA_OBJECT_STORAGE_EDGE_PORT}"
BETA_REC_MODEL_PORT="${BETA_REC_MODEL_PORT}"
BETA_POSTGRES_DSN="postgres://quwoquan:quwoquan@127.0.0.1:${BETA_POSTGRES_PORT}/quwoquan?sslmode=disable"
export CONTENT_PORT USER_PORT
export BETA_POSTGRES_PORT BETA_MONGO_PORT BETA_REDIS_PORT
BETA_SERVICE_CONFIG_ROOT="$RUNTIME_CONFIG_DIR/config-root"
BETA_MODEL_CACHE_ROOT="$CACHE_DIR/model"
eval "$(PYTHONPATH="$ROOT_DIR" python3 -m quwoquan_ops.cli.lib.local_beta_object_storage --shell "$BETA_OBJECT_STORAGE_EDGE_PORT")"
export BETA_OBJECT_STORAGE_EDGE_PORT BETA_REC_MODEL_PORT \
  BETA_SERVICE_CONFIG_ROOT BETA_MODEL_CACHE_ROOT
GATEWAY_BASE_URL_EXPLICIT=0
if [[ -n "${GATEWAY_BASE_URL:-}" ]]; then
  GATEWAY_BASE_URL_EXPLICIT=1
else
  GATEWAY_BASE_URL="$CANONICAL_GATEWAY_BASE_URL"
fi
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-}"
INTERNAL_CONTENT_BASE_URL="http://127.0.0.1:${CONTENT_PORT}"
INTERNAL_MEDIA_BASE_URL="http://127.0.0.1:${MEDIA_PROCESSOR_PORT}"
SKIP_BUILD=0
RESTART_STACK=1
CLEAN_ENV=0

BETA_MANUAL_LABEL="app-beta-manual"
BETA_MANUAL_STACK_NAME="beta-local"
BETA_MANUAL_LOG_DIR="$LOG_DIR"
BETA_MANUAL_STATE_DIR="${QWQ_OUTPUT_ROOT}/env/beta/local/beta-local/process"
BETA_MANUAL_RUNTIME_LOG_PROCESS="$ROOT_DIR/quwoquan_ops/cli/lib/runtime_log_process.py"
INSTANCE_NAMESPACE="${INSTANCE_NAMESPACE:-beta-local}"
BETA_MANUAL_OWNER_ID="${BETA_MANUAL_STACK_NAME}-$$-$(date +%s)"
export BETA_MANUAL_OWNER_ID BETA_MANUAL_RUNTIME_LOG_PROCESS
source "$ROOT_DIR/quwoquan_ops/cli/lib/beta_manual_lifecycle.sh"
TLS_PROXY_NAME="quwoquan_beta_tls_proxy"
TLS_PROXY_CADDYFILE="$RUNTIME_CONFIG_DIR/beta-public-plane.Caddyfile"
TLS_PROXY_DATA_VOLUME="${TLS_PROXY_DATA_VOLUME:-quwoquan_beta_local_caddy_data}"
TLS_PROXY_CONFIG_VOLUME="${TLS_PROXY_CONFIG_VOLUME:-quwoquan_beta_local_caddy_config}"
TLS_PROXY_PORT_RELEASE_TIMEOUT_SECONDS="${TLS_PROXY_PORT_RELEASE_TIMEOUT_SECONDS:-30}"
CONTAINER_RUNTIME=""
CONTAINER_HOST_ALIAS=""

usage() {
  cat <<EOF
Usage:
  quwoquan_app/scripts/tools/device/beta_manual_app.sh [options]

Default:
  Start the Beta release-consumer data plane. Business objects must already
  come from an immutable release activation; this entrypoint never seeds them.

Options:
  --gateway-base-url <url>   Gateway URL injected into Flutter app.
  --media-avatar-base-url <url>  Avatar authority injected into Flutter app.
  --media-image-base-url <url>   Image authority injected into Flutter app.
  --media-video-base-url <url>   Video authority injected into Flutter app.
  --media-upload-base-url <url>  Upload authority injected into Flutter app.
  --skip-build               Reuse existing Compose images without rebuilding.
  --content-release          Explicitly select the only supported release slice.
  --restart                  Stop a managed previous stack before starting (default on).
  --clean-env                Remove runtime pid/env state before starting.
  -h, --help                 Show this help.

This is an internal stackctl runner. App launch and user-acceptance execution
remain separate stackctl stages so an empty or unimported environment cannot be
reported as a successful business readback.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gateway-base-url)
      GATEWAY_BASE_URL="${2:-}"
      GATEWAY_BASE_URL_EXPLICIT=1
      shift 2
      ;;
    --media-avatar-base-url)
      MEDIA_AVATAR_CDN_BASE_URL="${2:-}"
      shift 2
      ;;
    --media-image-base-url)
      MEDIA_IMAGE_CDN_BASE_URL="${2:-}"
      shift 2
      ;;
    --media-video-base-url)
      MEDIA_VIDEO_CDN_BASE_URL="${2:-}"
      shift 2
      ;;
    --media-upload-base-url)
      MEDIA_UPLOAD_BASE_URL="${2:-}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --content-release)
      shift
      ;;
    --restart)
      RESTART_STACK=1
      shift
      ;;
    --clean-env)
      CLEAN_ENV=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

assert_canonical_url() {
  local label="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" != "$expected" ]]; then
    echo "GATE_BLOCK: beta $label URL override must equal topology projection" >&2
    exit 2
  fi
}
assert_canonical_url gateway "$GATEWAY_BASE_URL" "$CANONICAL_GATEWAY_BASE_URL"
assert_canonical_url legal "${LEGAL_BASE_URL:-$CANONICAL_LEGAL_BASE_URL}" "$CANONICAL_LEGAL_BASE_URL"
assert_canonical_url avatar "${MEDIA_AVATAR_CDN_BASE_URL:-$CANONICAL_MEDIA_AVATAR_BASE_URL}" "$CANONICAL_MEDIA_AVATAR_BASE_URL"
assert_canonical_url image "${MEDIA_IMAGE_CDN_BASE_URL:-$CANONICAL_MEDIA_IMAGE_BASE_URL}" "$CANONICAL_MEDIA_IMAGE_BASE_URL"
assert_canonical_url video "${MEDIA_VIDEO_CDN_BASE_URL:-$CANONICAL_MEDIA_VIDEO_BASE_URL}" "$CANONICAL_MEDIA_VIDEO_BASE_URL"
assert_canonical_url upload "${MEDIA_UPLOAD_BASE_URL:-$CANONICAL_MEDIA_UPLOAD_BASE_URL}" "$CANONICAL_MEDIA_UPLOAD_BASE_URL"

tls_exports="$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/lib/public_domain_tls.py" paths \
    --target beta-local \
    --format shell
)" || exit $?
eval "$tls_exports"

parse_mongo_host_port() {
  python3 - "$1" <<'PY'
import re
import sys
from urllib.parse import urlparse

raw = (sys.argv[1] or "").strip()
if not raw:
    print("localhost 27017")
    raise SystemExit(0)
parsed = urlparse(raw)
host = parsed.hostname or "localhost"
port = parsed.port or 27017
print(f"{host} {port}")
PY
}

parse_redis_host_port() {
  python3 - "$1" <<'PY'
import sys

raw = (sys.argv[1] or "").strip()
if not raw:
    print("localhost 6379")
    raise SystemExit(0)
host, _, port = raw.partition(":")
host = host.strip() or "localhost"
port = (port.strip() or "6379")
print(f"{host} {port}")
PY
}

beta_manual_check_mongo() {
  local uri="$1"
  local host port
  read -r host port <<< "$(parse_mongo_host_port "$uri")"
  if command -v mongosh >/dev/null 2>&1; then
    mongosh --quiet "$uri" --eval "db.adminCommand({ ping: 1 }).ok" >/dev/null 2>&1 && return 0
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z "$host" "$port" >/dev/null 2>&1 && return 0
  fi
  return 1
}

beta_manual_check_redis() {
  local addr="$1"
  local host port
  read -r host port <<< "$(parse_redis_host_port "$addr")"
  if command -v redis-cli >/dev/null 2>&1; then
    redis-cli -h "$host" -p "$port" ping >/dev/null 2>&1 && return 0
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z "$host" "$port" >/dev/null 2>&1 && return 0
  fi
  return 1
}

beta_manual_check_postgres() {
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h 127.0.0.1 -p "$BETA_POSTGRES_PORT" -U quwoquan >/dev/null 2>&1 && return 0
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$BETA_POSTGRES_PORT" >/dev/null 2>&1 && return 0
  fi
  return 1
}

beta_manual_wait_mongo_ready() {
  local uri="$1"
  local label="$2"
  local timeout="${3:-60}"
  local deadline=$((SECONDS + timeout))
  until beta_manual_check_mongo "$uri"; do
    if (( SECONDS >= deadline )); then
      echo "${label} unavailable: $uri" >&2
      return 1
    fi
    sleep 2
  done
}

beta_manual_wait_postgres_ready() {
  local timeout="${1:-90}"
  local deadline=$((SECONDS + timeout))
  until beta_manual_check_postgres; do
    if (( SECONDS >= deadline )); then
      echo "beta postgres unavailable: $BETA_POSTGRES_DSN" >&2
      return 1
    fi
    sleep 2
  done
}

beta_manual_wait_redis_ready() {
  local addr="$1"
  local label="$2"
  local timeout="${3:-60}"
  local deadline=$((SECONDS + timeout))
  until beta_manual_check_redis "$addr"; do
    if (( SECONDS >= deadline )); then
      echo "${label} unavailable: $addr" >&2
      return 1
    fi
    sleep 2
  done
}

beta_manual_prepare_service_config_root() {
  rm -rf "$BETA_SERVICE_CONFIG_ROOT"
  mkdir -p "$BETA_SERVICE_CONFIG_ROOT"
  local service package_dir config_file provenance_file config_version
  for service in content-service entity-service recommendation-service user-service; do
    PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" \
      package --env beta --service "$service" >/dev/null
    package_dir="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - "$service" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir

print(service_deployment_package_dir("beta", sys.argv[1]))
PY
)"
    config_file="$package_dir/config/config.yaml"
    provenance_file="$package_dir/provenance.json"
    if [[ ! -f "$config_file" || ! -f "$provenance_file" ]]; then
      echo "beta autonomous service package is incomplete for ${service}: ${package_dir}" >&2
      return 1
    fi
    config_version="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$service" "$config_file" "$provenance_file" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

service, config_value, provenance_value = sys.argv[1:4]
config_path = Path(config_value)
provenance_path = Path(provenance_value)
provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
actual = "sha256:" + hashlib.sha256(config_path.read_bytes()).hexdigest()
if provenance.get("service") != service or provenance.get("environment") != "beta":
    raise SystemExit(f"service package identity mismatch: {provenance_path}")
if (provenance.get("digests") or {}).get("config") != actual:
    raise SystemExit(f"service package config digest mismatch: {config_path}")
version = str(provenance.get("configVersion") or "")
if not re.fullmatch(r"sha256:[0-9a-f]{64}", version):
    raise SystemExit(f"invalid derived config version: {provenance_path}")
print(version)
PY
)" || return 1
    cp "$config_file" "$BETA_SERVICE_CONFIG_ROOT/${service}.yaml"
    case "$service" in
      content-service) export CONTENT_CONFIG_VERSION="$config_version" ;;
      recommendation-service) export RECOMMENDATION_CONFIG_VERSION="$config_version" ;;
      user-service) export USER_CONFIG_VERSION="$config_version" ;;
    esac
  done
  mkdir -p "$BETA_MODEL_CACHE_ROOT"
}

beta_manual_export_service_compose_environment() {
  local require_versions="${1:-true}"
  local content_version="${CONTENT_CONFIG_VERSION:-}"
  local recommendation_version="${RECOMMENDATION_CONFIG_VERSION:-}"
  local user_version="${USER_CONFIG_VERSION:-}"
  if [[ "$require_versions" == "true" ]]; then
    : "${content_version:?CONTENT_CONFIG_VERSION is required}"
    : "${recommendation_version:?RECOMMENDATION_CONFIG_VERSION is required}"
    : "${user_version:?USER_CONFIG_VERSION is required}"
  else
    content_version="${content_version:-sha256:0000000000000000000000000000000000000000000000000000000000000000}"
    recommendation_version="${recommendation_version:-sha256:0000000000000000000000000000000000000000000000000000000000000000}"
    user_version="${user_version:-sha256:0000000000000000000000000000000000000000000000000000000000000000}"
  fi
  export QWQ_COMPOSE_ENV=beta
  export QWQ_COMPOSE_CONFIG_ROOT="$BETA_SERVICE_CONFIG_ROOT"
  export QWQ_COMPOSE_MODEL_CACHE_ROOT="$BETA_MODEL_CACHE_ROOT"
  export QWQ_COMPOSE_CONTENT_SERVICE_CONFIG_VERSION="$content_version"
  export QWQ_COMPOSE_RECOMMENDATION_SERVICE_CONFIG_VERSION="$recommendation_version"
  export QWQ_COMPOSE_USER_SERVICE_CONFIG_VERSION="$user_version"
  export QWQ_COMPOSE_CONTENT_PORT="$CONTENT_PORT"
  export QWQ_COMPOSE_USER_PORT="$USER_PORT"
  export QWQ_COMPOSE_REC_MODEL_PORT="$BETA_REC_MODEL_PORT"
  export QWQ_COMPOSE_MONGO_URI="mongodb://mongodb:27017/?replicaSet=rs0"
  export QWQ_COMPOSE_MONGODB_URI="mongodb://mongodb:27017/?replicaSet=rs0"
  export QWQ_COMPOSE_SEARCH_ES_ENABLED=false
  export QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT="$BETA_OBJECT_STORAGE_ENDPOINT"
  export QWQ_COMPOSE_OBJECT_STORAGE_BUCKET="$BETA_OBJECT_STORAGE_BUCKET"
  export QWQ_COMPOSE_OBJECT_STORAGE_REGION="$BETA_OBJECT_STORAGE_REGION"
  export QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID="$BETA_OBJECT_STORAGE_ACCESS_KEY_ID"
  export QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET="$BETA_OBJECT_STORAGE_ACCESS_KEY_SECRET"
  export QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL="${CANONICAL_MEDIA_IMAGE_BASE_URL%/media/image}"
  export QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL="$CANONICAL_MEDIA_UPLOAD_BASE_URL"
  export QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY="$BETA_OBJECT_STORAGE_CDN_SIGN_KEY"
  export QWQ_COMPOSE_EMBEDDING_ENDPOINT="${CONTENT_EMBEDDING_ENDPOINT:-}"
  export QWQ_COMPOSE_EMBEDDING_API_KEY="${CONTENT_EMBEDDING_API_KEY:-}"
  export QWQ_COMPOSE_REC_POLICY_SOURCE="$ROOT_DIR/quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
}

beta_manual_compose_up_data_plane() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "beta content data plane is unavailable because docker is not installed" >&2
    return 1
  fi
  if [[ ! -f "$BETA_BACKING_COMPOSE_FILE" ]]; then
    echo "beta backing compose file missing: $BETA_BACKING_COMPOSE_FILE" >&2
    return 1
  fi
  beta_manual_prepare_service_config_root || return 1
  beta_manual_export_service_compose_environment
  echo "[app-beta-manual] starting real beta content data plane"
  # 切换到内容发布 slice 时清理已从当前 compose 拓扑退役的完整工作负载
  # 容器，避免孤儿模型服务与 MongoDB 抢占本机资源并使健康检查失真。
  # `:local` image 名称不是源码身份；每次启动都让 Compose 按当前工作树
  # 重新求值 build graph，并由 Docker layer cache 复用未变化的层。串行构建
  # 避免 content/user/recommendation 同时编译造成 Colima 内存峰值。
  local compose_up_args=(up -d --remove-orphans)
  if [[ "$SKIP_BUILD" == "1" ]]; then
    compose_up_args+=(--no-build)
  else
    compose_up_args+=(--build)
  fi
  local compose_output=""
  local attempt
  for attempt in 1 2 3; do
    if compose_output="$(COMPOSE_PARALLEL_LIMIT=1 docker compose -p "$BETA_BACKING_COMPOSE_PROJECT_NAME" "${BETA_BACKING_COMPOSE_ARGS[@]}" \
      "${compose_up_args[@]}" postgres mongodb mongo-init redis object-storage object-storage-init \
      recommendation-service content-service user-service 2>&1)"; then
      return 0
    fi
    printf '%s\n' "$compose_output" >&2
    if ! grep -Eq 'dependency failed to start: container .*mongodb.* is unhealthy' <<<"$compose_output"; then
      return 1
    fi
    if (( attempt == 3 )); then
      return 1
    fi
    echo "[app-beta-manual] MongoDB health check is still warming; retrying content data plane (${attempt}/3)" >&2
    sleep 5
  done
}

beta_manual_stop_content_runtime() {
  if ! command -v docker >/dev/null 2>&1 || [[ ! -f "$BETA_BACKING_COMPOSE_FILE" ]]; then
    return 0
  fi
  beta_manual_export_service_compose_environment false
  docker compose -p "$BETA_BACKING_COMPOSE_PROJECT_NAME" "${BETA_BACKING_COMPOSE_ARGS[@]}" \
    stop content-service recommendation-service user-service object-storage >/dev/null 2>&1 || true
}

beta_manual_require_content_embedding_binding() {
  if [[ -z "${CONTENT_EMBEDDING_ENDPOINT:-}" || -z "${CONTENT_EMBEDDING_API_KEY:-}" ]]; then
    echo "GATE_BLOCK: stackctl did not inject protected Beta content embedding Provider material" >&2
    return 1
  fi
  export QWQ_COMPOSE_EMBEDDING_ENDPOINT="${CONTENT_EMBEDDING_ENDPOINT}"
  export QWQ_COMPOSE_EMBEDDING_API_KEY="${CONTENT_EMBEDDING_API_KEY}"
}

beta_manual_ensure_docker_daemon() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker CLI unavailable; cannot start the beta data plane" >&2
    return 1
  fi
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if ! command -v colima >/dev/null 2>&1; then
    echo "docker daemon unavailable and colima is not installed" >&2
    return 1
  fi

  echo "[app-beta-manual] docker daemon unavailable, starting colima..."
  if ! colima start; then
    echo "colima start failed; please start a Docker daemon manually and retry" >&2
    return 1
  fi

  local deadline=$((SECONDS + 180))
  until docker info >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "docker daemon still unavailable after starting colima" >&2
      return 1
    fi
    sleep 2
  done
  echo "[app-beta-manual] docker daemon ready"
}

beta_manual_ensure_data_plane() {
  beta_manual_require_content_embedding_binding || return 1
  beta_manual_ensure_docker_daemon || return 1
  beta_manual_compose_up_data_plane || return 1
  local effective_mongo_uri="mongodb://127.0.0.1:${BETA_MONGO_PORT}/?directConnection=true"
  local effective_redis_addr="127.0.0.1:${BETA_REDIS_PORT}"
  beta_manual_wait_postgres_ready 90 || return 1
  beta_manual_wait_mongo_ready "$effective_mongo_uri" "beta MongoDB" 90 || return 1
  beta_manual_wait_redis_ready "$effective_redis_addr" "beta Redis" 90 || return 1
  beta_manual_wait_http_ok "${INTERNAL_CONTENT_BASE_URL}/healthz" "content-service" 300 || return 1
  beta_manual_wait_http_ok "http://127.0.0.1:${USER_PORT}/healthz" "user-service" 300 || return 1
  echo "[app-beta-manual] beta Mongo/Redis/content/user runtime OK"
}

beta_manual_init
ENTITY_LOG="$LOG_DIR/entity-service/local/runtime.log"
MEDIA_LOG="$LOG_DIR/media-origin/local/runtime.log"
MEDIA_EDGE_LOG="$LOG_DIR/media-edge/local/runtime.log"
MEDIA_DIR="$CACHE_DIR/media"
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-$CANONICAL_MEDIA_AVATAR_BASE_URL}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-$CANONICAL_MEDIA_IMAGE_BASE_URL}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-$CANONICAL_MEDIA_VIDEO_BASE_URL}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-$CANONICAL_MEDIA_UPLOAD_BASE_URL}"
if [[ ! -f "$BETA_LEGAL_STATIC_ROOT/legal/user-agreement" ]]; then
  echo "GATE_BLOCK: beta legal-static package is missing user-agreement at $BETA_LEGAL_STATIC_ROOT" >&2
  exit 2
fi
mkdir -p "$RUNTIME_CONFIG_DIR" "$CACHE_DIR" "$LOG_DIR" "$QWQ_RUN_ROOT"

if [[ "$RESTART_STACK" == "1" || "$CLEAN_ENV" == "1" ]]; then
  echo "[app-beta-manual] restarting managed beta stack before launch"
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  elif command -v podman >/dev/null 2>&1; then
    podman rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  fi
  beta_manual_stop_stack "$CLEAN_ENV"
  beta_manual_stop_content_runtime
  beta_manual_init
fi

: >"$BETA_MANUAL_STATE_DIR/stack.state"
beta_manual_record_metadata "stack" "$BETA_MANUAL_STACK_NAME"
beta_manual_record_metadata "controller_pid" "$$"
beta_manual_record_metadata "owner_id" "$BETA_MANUAL_OWNER_ID"
beta_manual_record_metadata "workload" "content-release"
beta_manual_record_metadata "entity_port" "$ENTITY_PORT"
beta_manual_record_metadata "content_port" "$CONTENT_PORT"
beta_manual_record_metadata "user_port" "$USER_PORT"
beta_manual_record_metadata "gateway_port" "$GATEWAY_PORT"
beta_manual_record_metadata "gateway_base_url" "$GATEWAY_BASE_URL"
beta_manual_record_metadata "media_port" "$MEDIA_PORT"
beta_manual_record_metadata "media_origin_port" "$MEDIA_ORIGIN_PORT"
beta_manual_record_metadata "media_avatar_cdn_base_url" "$MEDIA_AVATAR_CDN_BASE_URL"

resolve_container_runtime() {
  if [[ -n "$CONTAINER_RUNTIME" ]]; then
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    CONTAINER_RUNTIME="docker"
    CONTAINER_HOST_ALIAS="host.docker.internal"
    return 0
  fi
  if command -v podman >/dev/null 2>&1; then
    CONTAINER_RUNTIME="podman"
    CONTAINER_HOST_ALIAS="host.containers.internal"
    return 0
  fi
  echo "GATE_BLOCK: docker/podman not found; beta HTTPS public plane cannot start" >&2
  exit 2
}

beta_manual_prepare_tls_caddyfile() {
  resolve_container_runtime
  mkdir -p "$(dirname "$TLS_PROXY_CADDYFILE")"
  cat >"$TLS_PROXY_CADDYFILE" <<EOF
{
	admin off
}

(public_tls) {
	tls /etc/caddy/tls/fullchain.pem /etc/caddy/tls/privkey.pem
}

(media_cors) {
	header {
		Access-Control-Allow-Origin "*"
		Access-Control-Allow-Methods "GET, HEAD, OPTIONS"
		Access-Control-Allow-Headers "*"
		Cross-Origin-Resource-Policy "cross-origin"
		Cache-Control "no-store"
	}
	@immutable_public_media {
		path_regexp immutable_public_media ^/media/(?:avatar|image|video|background|attachment)/s/(?:[^/]+/)+v[1-9][0-9]*/(?:[^/]+/)*[^/]+$
		vars_regexp canonical_media_query {http.request.uri.query} ^$
	}
	header @immutable_public_media {
		Cache-Control "public, max-age=31536000, immutable"
		X-QWQ-Media-Cache-Key "{http.request.uri.path}"
	}
}

https://${PUBLIC_API_HOST}:${GATEWAY_PORT},
https://${PUBLIC_WEB_HOST}:${GATEWAY_PORT} {
	import public_tls
	handle /legal/manifest.json {
		header {
			Cache-Control "public, max-age=300"
			X-Content-Type-Options "nosniff"
		}
		root * /srv/legal
		file_server
	}
	handle /legal/* {
		header {
			Cache-Control "public, max-age=300"
			X-Content-Type-Options "nosniff"
			Content-Type "text/html; charset=utf-8"
		}
		root * /srv/legal
		file_server
	}
	@web_api {
		host ${PUBLIC_WEB_HOST}
		path /api/*
	}
	uri @web_api strip_prefix /api
	handle /healthz {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@content_release path /content /content/* /config/app
	handle @content_release {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@content_filter_catalog_release path /internal/content/filter-catalog-releases /internal/content/filter-catalog-releases/*
	handle @content_filter_catalog_release {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@homepage_release path /homepages /homepages/* /homepage-claim-requests /homepage-status-reports
	handle @homepage_release {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${ENTITY_PORT}
	}
	@creator_profile_release path /auth /auth/* /user /user/* /users /users/*
	handle @creator_profile_release {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${USER_PORT}
	}
	respond 404
}

https://${PUBLIC_IMAGE_HOST}:${MEDIA_PORT},
https://${PUBLIC_UPLOAD_HOST}:${MEDIA_PORT} {
	import public_tls
	import media_cors
	reverse_proxy ${CONTAINER_HOST_ALIAS}:${MEDIA_PROCESSOR_PORT}
}
EOF
}

beta_manual_stop_tls_proxy() {
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  elif command -v podman >/dev/null 2>&1; then
    podman rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  fi
  local port deadline
  local ports=("$GATEWAY_PORT" "$MEDIA_PORT")
  deadline=$((SECONDS + TLS_PROXY_PORT_RELEASE_TIMEOUT_SECONDS))
  for port in "${ports[@]}"; do
    while [[ -n "$(beta_manual_port_pids "$port")" ]]; do
      if (( SECONDS >= deadline )); then
        echo "GATE_BLOCK: Caddy port :$port did not release after ${TLS_PROXY_PORT_RELEASE_TIMEOUT_SECONDS}s" >&2
        return 1
      fi
      sleep 0.5
    done
  done
}

beta_manual_start_tls_proxy() {
  echo "[app-beta-manual] preparing content release public ingress"
  if ! beta_manual_prepare_tls_caddyfile; then
    echo "GATE_BLOCK: beta Caddy configuration preparation failed" >&2
    return 1
  fi
  if ! beta_manual_stop_tls_proxy; then
    echo "GATE_BLOCK: beta Caddy previous deployment did not stop cleanly" >&2
    return 1
  fi
  echo "[app-beta-manual] starting content release public ingress"
  local publish_args=(
    -p "${GATEWAY_PORT}:${GATEWAY_PORT}"
    -p "${MEDIA_PORT}:${MEDIA_PORT}"
  )
  local container_id
  if ! container_id="$("$CONTAINER_RUNTIME" run -d \
    --name "$TLS_PROXY_NAME" \
    -v "$TLS_PROXY_CADDYFILE:/etc/caddy/Caddyfile:ro" \
    -v "$QWQ_PUBLIC_TLS_CERT_FILE:/etc/caddy/tls/fullchain.pem:ro" \
    -v "$QWQ_PUBLIC_TLS_KEY_FILE:/etc/caddy/tls/privkey.pem:ro" \
    -v "$BETA_LEGAL_STATIC_ROOT:/srv/legal:ro" \
    -v "$TLS_PROXY_DATA_VOLUME:/data" \
    -v "$TLS_PROXY_CONFIG_VOLUME:/config" \
    "${publish_args[@]}" \
    docker.io/library/caddy:2.8.4-alpine 2>&1)"; then
    echo "GATE_BLOCK: beta Caddy deployment failed: ${container_id}" >&2
    return 1
  fi
  if [[ "$("$CONTAINER_RUNTIME" inspect --format '{{.State.Running}}' "$TLS_PROXY_NAME" 2>/dev/null || true)" != "true" ]]; then
    echo "GATE_BLOCK: beta Caddy deployment exited before readiness: ${container_id}" >&2
    "$CONTAINER_RUNTIME" logs --tail 80 "$TLS_PROXY_NAME" >&2 || true
    return 1
  fi
  echo "[app-beta-manual] content release public ingress started"
}

beta_manual_wait_https_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local label="$4"
  local timeout="${5:-30}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS \
    "https://${host}:${port}${path}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "${label} unavailable: https://${host}:${port}${path}" >&2
      return 1
    fi
    sleep 0.5
  done
}

beta_manual_verify_legal_document() {
  local host="$1"
  local port="$2"
  local path="$3"
  local expected_title="$4"
  local content_type=""
  local body=""
  content_type="$(
    curl -fsSI \
      "https://${host}:${port}${path}" \
      | tr -d '\r' \
      | awk -F ': ' 'tolower($1) == "content-type" { print tolower($2); exit }'
  )"
  if [[ "$content_type" != "text/html; charset=utf-8" ]]; then
    echo "GATE_BLOCK: ${path} must return text/html; charset=utf-8, got ${content_type:-missing}" >&2
    return 1
  fi
  body="$(curl -fsS "https://${host}:${port}${path}")"
  if [[ "$body" != *"$expected_title"* ]]; then
    echo "GATE_BLOCK: ${path} is missing expected UTF-8 title ${expected_title}" >&2
    return 1
  fi
}

beta_manual_start_release_media_runtime() {
  # ship apply is the only writer of this directory.  Do not seed, copy, or
  # erase it here: doing so would replace an immutable release with fixtures.
  mkdir -p "$MEDIA_DIR"
  PYTHONDONTWRITEBYTECODE=1 python3 - "$MEDIA_DIR" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
for kind in ("avatar", "image", "video"):
    slice_root = root / "media" / kind / "s"
    if not slice_root.exists():
        continue
    for path in slice_root.rglob("*"):
        relative = path.relative_to(root)
        lowered_parts = {part.lower() for part in relative.parts}
        if lowered_parts & {"fixture", "fixtures", "mock", "seed", "test_fixtures"}:
            raise SystemExit(
                f"GATE_BLOCK: beta media root contains a non-release public slice: {relative}"
            )
        if path.is_symlink():
            raise SystemExit(
                f"GATE_BLOCK: beta release media must be materialized bytes, not a symlink: {relative}"
            )
PY
  echo "[app-beta-manual] starting release media origin on :$MEDIA_ORIGIN_PORT"
  beta_manual_start_process \
    "media-origin" \
    "$MEDIA_LOG" \
    "$ROOT_DIR" \
    python3 quwoquan_ops/cli/lib/local_media_origin.py \
      --listen-host 0.0.0.0 \
      --listen-port "$MEDIA_ORIGIN_PORT" \
      --root-dir "$MEDIA_DIR" \
      --server-label beta-release-media-origin
  beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/healthz" "release media origin" 30 || return 1
  echo "[app-beta-manual] starting release media edge on :$MEDIA_PROCESSOR_PORT"
  beta_manual_start_process \
    "media-edge" \
    "$MEDIA_EDGE_LOG" \
    "$ROOT_DIR" \
    python3 quwoquan_ops/cli/lib/http_reverse_proxy.py \
      --listen-host 0.0.0.0 \
      --listen-port "$MEDIA_PROCESSOR_PORT" \
      --target-base-url "http://127.0.0.1:${MEDIA_ORIGIN_PORT}"
  beta_manual_wait_http_ok "${INTERNAL_MEDIA_BASE_URL}/healthz" "release media edge" 30 || return 1
}

beta_manual_start_entity_service() {
  # Caddy is containerized; it reaches this local service through the host
  # gateway rather than the host loopback device.
  local listen_host="0.0.0.0"
  echo "[app-beta-manual] starting entity-service beta on :$ENTITY_PORT"
  beta_manual_start_process \
    "entity-service" \
    "$ENTITY_LOG" \
    "$ENTITY_SERVICE_DIR" \
    env \
      APP_ENV=beta \
      CONFIG_ROOT="$BETA_SERVICE_CONFIG_ROOT" \
      ENTITY_SERVICE_ADDR="${listen_host}:${ENTITY_PORT}" \
      ENTITY_MONGO_URI="mongodb://127.0.0.1:${BETA_MONGO_PORT}/?directConnection=true" \
      ENTITY_MONGO_DATABASE=quwoquan_entity \
      ENTITY_REDIS_GENERAL_ADDR="127.0.0.1:${BETA_REDIS_PORT}" \
      ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL="http://127.0.0.1:${USER_PORT}" \
      SEARCH_ES_ENABLED=false \
      go run ./cmd/api

  # 首次启动时 `go run` 需要编译依赖图；content-release 不能在编译尚未
  # 完成时把健康检查超时误判成实体服务不可用。
  beta_manual_wait_http_ok "http://127.0.0.1:${ENTITY_PORT}/healthz" "entity-service" 180
}

beta_manual_start_content_release_stack() {
  beta_manual_ensure_data_plane || return 1
  beta_manual_start_release_media_runtime || return 1
  beta_manual_start_entity_service || return 1
  beta_manual_start_tls_proxy || return 1
  echo "[app-beta-manual] checking content release public API ingress"
  if ! beta_manual_wait_https_ok \
    "$PUBLIC_API_HOST" \
    "$GATEWAY_PORT" \
    "/healthz" \
    "content release public health" \
    30; then
    "$CONTAINER_RUNTIME" logs --tail 80 "$TLS_PROXY_NAME" >&2 || true
    return 1
  fi
  echo "[app-beta-manual] checking content release public media ingress"
  if ! beta_manual_wait_https_ok \
    "$PUBLIC_IMAGE_HOST" \
    "$MEDIA_PORT" \
    "/healthz" \
    "content release public media edge" \
    30; then
    "$CONTAINER_RUNTIME" logs --tail 80 "$TLS_PROXY_NAME" >&2 || true
    return 1
  fi
  beta_manual_wait_https_ok \
    "$PUBLIC_API_HOST" \
    "$GATEWAY_PORT" \
    "/legal/user-agreement" \
    "legal static user agreement" \
    30 || return 1
  beta_manual_verify_legal_document \
    "$PUBLIC_API_HOST" \
    "$GATEWAY_PORT" \
    "/legal/user-agreement" \
    "趣我圈用户协议" || return 1
  beta_manual_verify_legal_document \
    "$PUBLIC_API_HOST" \
    "$GATEWAY_PORT" \
    "/legal/privacy-policy" \
    "趣我圈隐私政策" || return 1
  python3 - "$REPORT" "$GATEWAY_BASE_URL" "$LEGAL_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

report_path, gateway_base_url, legal_base_url = sys.argv[1:]
report = {
    "schema": "qwq.beta-immutable-release-consumer-component",
    "status": "component_ready",
    "environment": "beta",
    "target": "beta-local",
    "composition": "production_remote",
    "gatewayBaseUrl": gateway_base_url,
    "legalBaseUrl": legal_base_url,
    "businessDataReady": False,
    "releaseEvidence": "required_before_business_readback",
}
Path(report_path).write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
  echo "[app-beta-manual] content release slice is ready."
  echo "[app-beta-manual] component report: $REPORT"
  beta_manual_wait_until_stopped media-edge media-origin entity-service
}

cleanup() {
  trap - EXIT INT TERM HUP TSTP
  beta_manual_stop_tls_proxy
  beta_manual_stop_stack "$CLEAN_ENV" "$BETA_MANUAL_OWNER_ID"
  beta_manual_stop_content_runtime
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM
trap 'cleanup; exit 129' HUP
trap 'cleanup; exit 148' TSTP

beta_manual_ensure_port_available "$GATEWAY_PORT" "gateway"
beta_manual_ensure_port_available "$CONTENT_PORT" "content-service"
beta_manual_ensure_port_available "$USER_PORT" "user-service"
beta_manual_ensure_port_available "$BETA_OBJECT_STORAGE_EDGE_PORT" "object-storage"
beta_manual_ensure_port_available "$ENTITY_PORT" "entity-service"
beta_manual_ensure_port_available "$MEDIA_PORT" "media-edge"
beta_manual_ensure_port_available "$MEDIA_PROCESSOR_PORT" "media-edge-upstream"
beta_manual_ensure_port_available "$MEDIA_ORIGIN_PORT" "media-origin"
echo "[app-beta-manual] starting the Beta immutable-release consumer slice"
beta_manual_start_content_release_stack || {
  echo "content release slice failed to become ready" >&2
  exit 1
}
