#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"
ASSISTANT_SERVICE_DIR="$ROOT_DIR/quwoquan_service/services/assistant-service"
CHAT_SERVICE_DIR="$ROOT_DIR/quwoquan_service/services/chat-service"
ENTITY_SERVICE_DIR="$ROOT_DIR/quwoquan_service/services/entity-service"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
if [[ -z "${QWQ_OBSERVABILITY_RUN_ROOT:-}" || -z "${QWQ_RUN_ROOT:-}" ]]; then
  eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_run.py" \
    --env beta --target beta-local --action up --output-root "$QWQ_OUTPUT_ROOT")"
fi
export QWQ_OUTPUT_ROOT QWQ_DEPLOY_WORK_ROOT QWQ_OBSERVABILITY_RUN_ROOT QWQ_RUN_ROOT
eval "$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/lib/public_domain_tls.py" paths \
    --target beta-local \
    --format shell
)"
RUNTIME_CONFIG_DIR="${QWQ_DEPLOY_WORK_ROOT}/beta-local/rendered"
CACHE_DIR="${QWQ_OUTPUT_ROOT}/env/beta/local/beta-local/cache"
LOG_DIR="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
REPORT="${QWQ_RUN_ROOT}/app-beta-manual-report.json"
MANIFEST="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/app_beta_seed_manifest.json"
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

ASSISTANT_PORT="${ASSISTANT_PORT}"
CHAT_PORT="${CHAT_PORT}"
ENTITY_PORT="${BETA_ENTITY_PORT}"
GATEWAY_PORT="${GATEWAY_PORT}"
PRODUCT_OPS_PORT="${PRODUCT_OPS_PORT}"
MEDIA_PORT="${MEDIA_PORT}"
MEDIA_ORIGIN_PORT="${MEDIA_ORIGIN_PORT}"
CONTENT_PORT="${CONTENT_PORT}"
USER_PORT="${USER_PORT}"
PRODUCT_OPS_SERVICE_PORT="${PRODUCT_OPS_SERVICE_PORT}"
MEDIA_PROCESSOR_PORT="${MEDIA_PROCESSOR_PORT}"
CHAT_SEED_REFS="${CHAT_SEED_REFS:-chat_core,chat_settings_core,chat_contacts_core,chat_group_flow_core}"
CHAT_MONGO_URI="${CHAT_MONGO_URI:-mongodb://localhost:27017/?directConnection=true}"
CHAT_MONGO_DATABASE="${CHAT_MONGO_DATABASE:-quwoquan_chat_local}"
CHAT_REDIS_ADDR="${CHAT_REDIS_ADDR:-localhost:6379}"
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
BETA_NOTIFICATION_PORT="${BETA_NOTIFICATION_PORT}"
BETA_FIXTURE_GATEWAY_PORT="${BETA_FIXTURE_GATEWAY_PORT}"
BETA_POSTGRES_DSN="postgres://quwoquan:quwoquan@127.0.0.1:${BETA_POSTGRES_PORT}/quwoquan?sslmode=disable"
export CONTENT_PORT USER_PORT
export BETA_POSTGRES_PORT BETA_MONGO_PORT BETA_REDIS_PORT
BETA_SERVICE_CONFIG_ROOT="$RUNTIME_CONFIG_DIR/config-root"
BETA_REPORT_ACCOUNT_BACKFILL_FILE="$BETA_SERVICE_CONFIG_ROOT/report-account-backfill.json"
BETA_MODEL_CACHE_ROOT="$CACHE_DIR/model"
eval "$(PYTHONPATH="$ROOT_DIR" python3 -m quwoquan_ops.cli.lib.local_beta_object_storage --shell "$BETA_OBJECT_STORAGE_EDGE_PORT")"
export BETA_OBJECT_STORAGE_EDGE_PORT BETA_REC_MODEL_PORT BETA_NOTIFICATION_PORT \
  BETA_FIXTURE_GATEWAY_PORT BETA_SERVICE_CONFIG_ROOT BETA_MODEL_CACHE_ROOT
GATEWAY_BASE_URL_EXPLICIT=0
if [[ -n "${GATEWAY_BASE_URL:-}" ]]; then
  GATEWAY_BASE_URL_EXPLICIT=1
else
  GATEWAY_BASE_URL="$CANONICAL_GATEWAY_BASE_URL"
fi
LOCAL_PUBLIC_HOST="${LOCAL_PUBLIC_HOST:-}"
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-}"
FIXTURE_GATEWAY_BASE_URL="http://127.0.0.1:${BETA_FIXTURE_GATEWAY_PORT}"
INTERNAL_GATEWAY_BASE_URL="$FIXTURE_GATEWAY_BASE_URL"
INTERNAL_CONTENT_BASE_URL="http://127.0.0.1:${CONTENT_PORT}"
INTERNAL_MEDIA_BASE_URL="http://127.0.0.1:${MEDIA_PROCESSOR_PORT}"
INTERNAL_PRODUCT_OPS_BASE_URL="http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}"
APP_CURRENT_USER_ID="${APP_CURRENT_USER_ID:-fixture_user_current}"
ASSISTANT_SEED_REFS="${ASSISTANT_SEED_REFS:-assistant_p0_core}"
FLUTTER_DEVICE_ID="${FLUTTER_DEVICE_ID:-}"
DEV_UP_HELPER="$ROOT_DIR/quwoquan_ops/cli/lib/dev_up.py"
SKIP_APP=0
SKIP_BUILD=0
START_ASSISTANT=1
CONTENT_RELEASE_ONLY=0
RESTART_STACK=1
CLEAN_ENV=0
VERIFY_MODE="${BETA_SEED_VERIFY_MODE:-fast}"
MEDIA_PREP_MODE="${BETA_MEDIA_PREP_MODE:-symlink}"

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
  quwoquan_app/scripts/device/start_app_beta_manual.sh [options]

Default:
  Restart the local beta cloud stack, then start the Flutter app.

Options:
  --device-id <id>           Flutter device id for manual beta run.
  --gateway-base-url <url>   Gateway URL injected into Flutter app.
                             iOS simulator default: http://127.0.0.1:${GATEWAY_PORT}
                             Android emulator usually: http://10.0.2.2:${GATEWAY_PORT}
  --local-public-host <host>  Host visible from the App device for gateway/media.
  --media-avatar-base-url <url>  Avatar authority injected into Flutter app.
  --media-image-base-url <url>   Image authority injected into Flutter app.
  --media-video-base-url <url>   Video authority injected into Flutter app.
  --media-upload-base-url <url>  Upload authority injected into Flutter app.
  --seed-verify <fast|full>   Seed verification mode before start (default: ${VERIFY_MODE}).
  --media-mode <symlink|copy> Media root preparation mode (default: ${MEDIA_PREP_MODE}).
  --full-matrix              Equivalent to --seed-verify full --media-mode copy.
  --skip-app                 Start/check beta cloud stack only; do not start Flutter.
  --skip-build               Reuse existing Compose images without rebuilding.
  --skip-assistant           Skip assistant-service for content-only validation.
  --content-release          Start only the real Content/Notification release slice.
  --restart                  Stop a managed previous stack before starting (default on).
  --clean-env                Remove runtime pid/env state before starting.
  -h, --help                 Show this help.

This is the single local beta manual entrypoint. With no arguments it stops
the previous managed beta stack, starts assistant-service, starts the unified
local beta gateway for business fixture routes, checks key cloud routes, and
then starts the Flutter app.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device-id)
      FLUTTER_DEVICE_ID="${2:-}"
      shift 2
      ;;
    --gateway-base-url)
      GATEWAY_BASE_URL="${2:-}"
      GATEWAY_BASE_URL_EXPLICIT=1
      shift 2
      ;;
    --local-public-host)
      LOCAL_PUBLIC_HOST="${2:-}"
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
    --seed-verify)
      VERIFY_MODE="${2:-}"
      shift 2
      ;;
    --media-mode)
      MEDIA_PREP_MODE="${2:-}"
      shift 2
      ;;
    --full-matrix)
      VERIFY_MODE="full"
      MEDIA_PREP_MODE="copy"
      shift
      ;;
    --skip-app)
      SKIP_APP=1
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --skip-assistant)
      START_ASSISTANT=0
      shift
      ;;
    --content-release)
      CONTENT_RELEASE_ONLY=1
      START_ASSISTANT=0
      SKIP_APP=1
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

if [[ "$CONTENT_RELEASE_ONLY" != "1" ]]; then
  echo "GATE_BLOCK: legacy Beta fixture workload is retired; use --content-release and activate an immutable release." >&2
  exit 2
fi

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
  for service in content-service entity-service notification-service recommendation-service user-service; do
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
  PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 \
    python3 -m quwoquan_ops.cli.lib.local_environment_auth \
      --write-report-account-backfill \
      beta \
      beta-local \
      "$BETA_REPORT_ACCOUNT_BACKFILL_FILE" >/dev/null
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
  export QWQ_COMPOSE_OBJECT_STORAGE_CDN_DOMAIN="$BETA_OBJECT_STORAGE_CDN_DOMAIN"
  export QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY="$BETA_OBJECT_STORAGE_CDN_SIGN_KEY"
  export QWQ_COMPOSE_OBJECT_STORAGE_CA_FILE="$BETA_OBJECT_STORAGE_CA_FILE"
  export QWQ_COMPOSE_EMBEDDING_ENDPOINT="${CONTENT_EMBEDDING_ENDPOINT:-}"
  export QWQ_COMPOSE_EMBEDDING_API_KEY="${CONTENT_EMBEDDING_API_KEY:-}"
  export QWQ_COMPOSE_REC_POLICY_SOURCE="$ROOT_DIR/quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy_object_cards_v1.yaml"
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

beta_manual_seed_user_fixtures() {
  local seed_config=""
  if ! seed_config="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$MANIFEST" "$ROOT_DIR" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
repo_root = Path(sys.argv[2]).resolve()
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
user_entries = [
    entry
    for entry in payload.get("seedRefs", [])
    if isinstance(entry, dict) and entry.get("domain") == "user"
]
if len(user_entries) != 1:
    raise SystemExit("beta seed manifest must declare exactly one user seed entry")
entry = user_entries[0]
if entry.get("resetScope") != "fixture_user_*":
    raise SystemExit("beta user seed resetScope must remain fixture_user_*")
fixture = str(entry.get("fixturePath") or "").strip()
fixture_path = Path(fixture)
expected_root = (
    repo_root
    / "quwoquan_service/services/user-service/tests/support/contract_fixtures"
).resolve()
resolved_fixture = (repo_root / fixture_path).resolve()
if (
    fixture_path.is_absolute()
    or ".." in fixture_path.parts
    or not resolved_fixture.is_relative_to(expected_root)
    or not resolved_fixture.is_file()
):
    raise SystemExit("beta user fixture path is outside the declared user fixture root")
refs = entry.get("refs")
if not isinstance(refs, list) or not refs or any(
    not isinstance(ref, str) or not ref.strip() for ref in refs
):
    raise SystemExit("beta user seed refs are missing or invalid")
print(resolved_fixture)
print(",".join(ref.strip() for ref in refs))
PY
)"; then
    return 1
  fi
  if [[ "$seed_config" != *$'\n'* ]]; then
    echo "beta user seed manifest projection is incomplete" >&2
    return 1
  fi
  local user_fixture="${seed_config%%$'\n'*}"
  local user_refs="${seed_config#*$'\n'}"
  echo "[app-beta-manual] resetting declared beta user fixtures: ${user_refs}"
  (
    cd "$ROOT_DIR/quwoquan_service"
    go run ./services/user-service/cmd/seed \
      --pg-dsn "$BETA_POSTGRES_DSN" \
      --fixture "$user_fixture" \
      --refs "$user_refs"
  )
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
  # Non-prod uses protocol_fixture; credentials are auto-materialized under
  # QWQ_DEPLOY_WORK_ROOT and exposed through compatibility aliases.
  if [[ -n "${CONTENT_EMBEDDING_ENDPOINT:-}" && -n "${CONTENT_EMBEDDING_API_KEY:-}" ]]; then
    return 0
  fi
  if [[ -n "${CONTENT_EMBEDDING_FIXTURE_ENDPOINT:-}" && -n "${CONTENT_EMBEDDING_FIXTURE_API_KEY:-}" ]]; then
    export CONTENT_EMBEDDING_ENDPOINT="${CONTENT_EMBEDDING_ENDPOINT:-$CONTENT_EMBEDDING_FIXTURE_ENDPOINT}"
    export CONTENT_EMBEDDING_API_KEY="${CONTENT_EMBEDDING_API_KEY:-$CONTENT_EMBEDDING_FIXTURE_API_KEY}"
    export QWQ_COMPOSE_EMBEDDING_ENDPOINT="${QWQ_COMPOSE_EMBEDDING_ENDPOINT:-$CONTENT_EMBEDDING_ENDPOINT}"
    export QWQ_COMPOSE_EMBEDDING_API_KEY="${QWQ_COMPOSE_EMBEDDING_API_KEY:-$CONTENT_EMBEDDING_API_KEY}"
    return 0
  fi

  local materializer_output
  if ! materializer_output="$(
    PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.local_provider_credentials import prepare_local_provider_credentials

values = prepare_local_provider_credentials(environment="beta", target_name="beta-local")
for key in (
    "CONTENT_EMBEDDING_FIXTURE_ENDPOINT",
    "CONTENT_EMBEDDING_FIXTURE_API_KEY",
):
    value = values.get(key, "")
    if value:
        print(f"{key}={value}")
PY
  )"; then
    echo "GATE_BLOCK: beta content embedding provider materialization failed" >&2
    return 1
  fi
  local line key value
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    export "$key=$value"
  done <<<"$materializer_output"
  export CONTENT_EMBEDDING_ENDPOINT="${CONTENT_EMBEDDING_FIXTURE_ENDPOINT:-}"
  export CONTENT_EMBEDDING_API_KEY="${CONTENT_EMBEDDING_FIXTURE_API_KEY:-}"
  export QWQ_COMPOSE_EMBEDDING_ENDPOINT="${CONTENT_EMBEDDING_ENDPOINT}"
  export QWQ_COMPOSE_EMBEDDING_API_KEY="${CONTENT_EMBEDDING_API_KEY}"
  if [[ -z "${CONTENT_EMBEDDING_ENDPOINT:-}" || -z "${CONTENT_EMBEDDING_API_KEY:-}" ]]; then
    echo "GATE_BLOCK: beta content embedding provider prerequisite is missing: CONTENT_EMBEDDING_ENDPOINT, CONTENT_EMBEDDING_API_KEY" >&2
    return 1
  fi
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
  CHAT_MONGO_URI="$effective_mongo_uri"
  CHAT_REDIS_ADDR="$effective_redis_addr"
  beta_manual_wait_http_ok "${INTERNAL_CONTENT_BASE_URL}/healthz" "content-service" 300 || return 1
  beta_manual_wait_http_ok "http://127.0.0.1:${USER_PORT}/healthz" "user-service" 300 || return 1
  echo "[app-beta-manual] beta Mongo/Redis/content/user runtime OK"
}

resolve_assistant_model_env() {
  python3 - <<'PY'
import os
import shlex
provider = os.environ.get("ASSISTANT_MODEL_PROVIDER", "deterministic").strip() or "deterministic"
base_url = os.environ.get("ASSISTANT_MODEL_BASE_URL", "").strip()
model_id = os.environ.get("ASSISTANT_MODEL_MODEL", "").strip()
api_key = os.environ.get("ASSISTANT_MODEL_API_KEY", "").strip()
if provider not in {"deterministic", "fake"} and (not base_url or not model_id or not api_key):
    print("echo 'GATE_BLOCK: real assistant model requires ASSISTANT_MODEL_BASE_URL, ASSISTANT_MODEL_MODEL and ASSISTANT_MODEL_API_KEY' >&2")
    print("exit 2")
    raise SystemExit(0)
ref = os.environ.get("ASSISTANT_BETA_MODEL_REF", provider if provider in {"deterministic", "fake"} else f"{provider}/{model_id}")
print(f"ASSISTANT_MODEL_PROVIDER={shlex.quote(provider)}")
print(f"ASSISTANT_MODEL_BASE_URL={shlex.quote(base_url)}")
print(f"ASSISTANT_MODEL_MODEL={shlex.quote(model_id)}")
print("ASSISTANT_MODEL_API_KEY_ENV=ASSISTANT_BETA_RESOLVED_MODEL_API_KEY")
print(f"ASSISTANT_BETA_RESOLVED_MODEL_API_KEY={shlex.quote(api_key)}")
print(f"ASSISTANT_BETA_MODEL_REF={shlex.quote(ref)}")
print(f"ASSISTANT_BETA_MODEL_SOURCE_PROVIDER={shlex.quote(provider)}")
PY
}

if [[ "$START_ASSISTANT" == "1" ]]; then
  eval "$(resolve_assistant_model_env)"
  if [[ "${ASSISTANT_MODEL_PROVIDER}" == "deterministic" || "${ASSISTANT_MODEL_PROVIDER}" == "fake" ]]; then
    echo "GATE_BLOCK: beta assistant-service requires a real model provider; use --skip-assistant only for content-only validation." >&2
    exit 2
  fi
  if [[ -z "${ASSISTANT_BETA_RESOLVED_MODEL_API_KEY:-}" ]]; then
    echo "GATE_BLOCK: no assistant beta model key resolved from environment." >&2
    exit 2
  fi
else
  ASSISTANT_MODEL_PROVIDER=""
  ASSISTANT_MODEL_BASE_URL=""
  ASSISTANT_MODEL_MODEL=""
  ASSISTANT_MODEL_API_KEY_ENV=""
  ASSISTANT_BETA_RESOLVED_MODEL_API_KEY=""
  ASSISTANT_BETA_MODEL_REF="disabled"
fi

beta_manual_init
RESTARTED_FROM_PREVIOUS=0
if [[ -f "$BETA_MANUAL_STATE_DIR/stack.state" ]] || [[ -n "$(beta_manual_port_pids "$GATEWAY_PORT")" ]] || [[ -n "$(beta_manual_port_pids "$MEDIA_PORT")" ]] || [[ -n "$(beta_manual_port_pids "$ASSISTANT_PORT")" ]] || [[ -n "$(beta_manual_port_pids "$CHAT_PORT")" ]] || [[ -n "$(beta_manual_port_pids "$ENTITY_PORT")" ]]; then
  RESTARTED_FROM_PREVIOUS=1
fi
ASSISTANT_LOG="$LOG_DIR/assistant-service/local/runtime.log"
CHAT_LOG="$LOG_DIR/chat-service/local/runtime.log"
ENTITY_LOG="$LOG_DIR/entity-service/local/runtime.log"
CHAT_SEED_LOG="$LOG_DIR/chat-seed/local/runtime.log"
GATEWAY_LOG="$LOG_DIR/api-edge/local/runtime.log"
NOTIFICATION_LOG="$LOG_DIR/notification-service/local/runtime.log"
MEDIA_LOG="$LOG_DIR/media-origin/local/runtime.log"
MEDIA_EDGE_LOG="$LOG_DIR/media-edge/local/runtime.log"
MEDIA_DIR="$CACHE_DIR/media"
SOURCE_MEDIA_ROOT="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
CANONICAL_SOURCE_MEDIA_ROOT="$SOURCE_MEDIA_ROOT"
if [[ -d "$SOURCE_MEDIA_ROOT/media" ]]; then
  CANONICAL_SOURCE_MEDIA_ROOT="$SOURCE_MEDIA_ROOT/media"
fi
detect_device_kind() {
  local device_id="$1"
  if [[ -z "$device_id" ]]; then
    echo "ios_or_macos"
    return
  fi
  if [[ "$device_id" == emulator-* || "$device_id" == *"Android SDK"* ]]; then
    echo "android_emulator"
    return
  fi
  if command -v adb >/dev/null 2>&1 && adb -s "$device_id" get-state >/dev/null 2>&1; then
    echo "android_physical"
    return
  fi
  echo "ios_or_macos"
}

resolve_single_flutter_device() {
  python3 "$DEV_UP_HELPER" pick-device --app-dir "$ROOT_DIR/quwoquan_app"
}

if [[ "$SKIP_APP" != "1" && -z "$FLUTTER_DEVICE_ID" ]]; then
  FLUTTER_DEVICE_ID="$(resolve_single_flutter_device)"
fi

DEVICE_KIND="$(detect_device_kind "$FLUTTER_DEVICE_ID")"
ADB_REVERSE_ENABLED=0
if [[ -z "$LOCAL_PUBLIC_HOST" ]]; then
  LOCAL_PUBLIC_HOST="$PUBLIC_API_HOST"
fi
if [[ "$GATEWAY_BASE_URL_EXPLICIT" == "0" ]]; then
  GATEWAY_BASE_URL="https://${PUBLIC_API_HOST}:${GATEWAY_PORT}"
fi
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-$CANONICAL_MEDIA_AVATAR_BASE_URL}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-$CANONICAL_MEDIA_IMAGE_BASE_URL}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-$CANONICAL_MEDIA_VIDEO_BASE_URL}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-$CANONICAL_MEDIA_UPLOAD_BASE_URL}"

case "$VERIFY_MODE" in
  fast|full) ;;
  *)
    echo "FAIL: --seed-verify must be fast|full" >&2
    exit 2
    ;;
esac

case "$MEDIA_PREP_MODE" in
  symlink|copy) ;;
  *)
    echo "FAIL: --media-mode must be symlink|copy" >&2
    exit 2
    ;;
esac

python3 "$ROOT_DIR/quwoquan_app/scripts/env/verify_app_seed_manifests.py"
bash "$ROOT_DIR/quwoquan_app/scripts/env/build_app_env_package.sh" --env beta >/dev/null
if [[ "$START_ASSISTANT" == "1" ]]; then
  bash "$ROOT_DIR/quwoquan_service/scripts/runtime/build_service_env_package.sh" --service assistant-service --env beta >/dev/null
fi
python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" package --env beta --kind legal-static >/dev/null
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
beta_manual_record_metadata "workload" "$([[ "$CONTENT_RELEASE_ONLY" == "1" ]] && printf '%s' content-release || printf '%s' full)"
beta_manual_record_metadata "assistant_enabled" "$START_ASSISTANT"
beta_manual_record_metadata "assistant_port" "$ASSISTANT_PORT"
beta_manual_record_metadata "chat_port" "$CHAT_PORT"
beta_manual_record_metadata "entity_port" "$ENTITY_PORT"
beta_manual_record_metadata "content_port" "$CONTENT_PORT"
beta_manual_record_metadata "user_port" "$USER_PORT"
if [[ "$CONTENT_RELEASE_ONLY" != "1" ]]; then
  beta_manual_record_metadata "notification_port" "$BETA_NOTIFICATION_PORT"
  beta_manual_record_metadata "fixture_gateway_port" "$BETA_FIXTURE_GATEWAY_PORT"
fi
beta_manual_record_metadata "gateway_port" "$GATEWAY_PORT"
beta_manual_record_metadata "gateway_base_url" "$GATEWAY_BASE_URL"
beta_manual_record_metadata "flutter_device_id" "$FLUTTER_DEVICE_ID"
beta_manual_record_metadata "device_kind" "$DEVICE_KIND"
beta_manual_record_metadata "local_public_host" "$LOCAL_PUBLIC_HOST"
beta_manual_record_metadata "media_port" "$MEDIA_PORT"
beta_manual_record_metadata "media_origin_port" "$MEDIA_ORIGIN_PORT"
beta_manual_record_metadata "media_avatar_cdn_base_url" "$MEDIA_AVATAR_CDN_BASE_URL"
beta_manual_record_metadata "seed_verify_mode" "$VERIFY_MODE"
beta_manual_record_metadata "media_prep_mode" "$MEDIA_PREP_MODE"

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
  if [[ "$CONTENT_RELEASE_ONLY" == "1" ]]; then
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
	}
}

https://${PUBLIC_API_HOST}:${GATEWAY_PORT},
https://${PUBLIC_WEB_HOST}:${GATEWAY_PORT} {
	import public_tls
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
    return 0
  fi
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
	handle /healthz {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@content_report path /content/reports /content/reports/* /content/users/me/reports
	handle @content_report {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@content_behavior path /content/behaviors
	handle @content_behavior {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@content_filter_catalog path /content/filter-catalog
	handle @content_filter_catalog {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@content_filter_catalog_release path /internal/content/filter-catalog-releases /internal/content/filter-catalog-releases/*
	handle @content_filter_catalog_release {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
	@notification_app_messages path /app-messages /app-messages/*
	handle @notification_app_messages {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${BETA_NOTIFICATION_PORT}
	}
	handle {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${BETA_FIXTURE_GATEWAY_PORT}
	}
}

https://${PUBLIC_PRODUCT_OPS_HOST}:${PRODUCT_OPS_PORT} {
	import public_tls
	reverse_proxy ${CONTAINER_HOST_ALIAS}:${PRODUCT_OPS_SERVICE_PORT}
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
  if [[ "$CONTENT_RELEASE_ONLY" != "1" ]]; then
    ports+=("$PRODUCT_OPS_PORT")
  fi
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
  if [[ "$CONTENT_RELEASE_ONLY" != "1" ]]; then
    publish_args+=( -p "${PRODUCT_OPS_PORT}:${PRODUCT_OPS_PORT}" )
  fi
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
  body="$(
    curl -fsS \
      "https://${host}:${port}${path}"
  )"
  if [[ "$body" != *"$expected_title"* ]]; then
    echo "GATE_BLOCK: ${path} is missing expected UTF-8 title ${expected_title}" >&2
    return 1
  fi
}

beta_manual_wait_https_range_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local label="$4"
  local timeout="${5:-30}"
  local deadline=$((SECONDS + timeout))
  local status=""
  until [[ "$status" == "206" ]]; do
    status="$(
      curl -fsS \
        -r 0-1 \
        -o /dev/null \
        -w '%{http_code}' \
        "https://${host}:${port}${path}" 2>/dev/null || true
    )"
    if (( SECONDS >= deadline )); then
      echo "${label} unavailable: https://${host}:${port}${path}" >&2
      return 1
    fi
    sleep 0.5
  done
}

beta_manual_start_fixture_gateway() {
  echo "[app-beta-manual] starting beta fixture gateway on :$BETA_FIXTURE_GATEWAY_PORT"
  local content_upstream_args=()
  if [[ "$CONTENT_RELEASE_ONLY" == "1" ]]; then
    content_upstream_args=(
      --content-upstream-host 127.0.0.1
      --content-upstream-port "$CONTENT_PORT"
    )
  fi
  beta_manual_start_process \
    "gateway" \
    "$GATEWAY_LOG" \
    "$ROOT_DIR" \
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/smoke/dev_assistant_beta_gateway.py \
      --listen-host 127.0.0.1 \
      --listen-port "$BETA_FIXTURE_GATEWAY_PORT" \
      --assistant-upstream-host 127.0.0.1 \
      --assistant-upstream-port "$ASSISTANT_PORT" \
      --chat-upstream-host 127.0.0.1 \
      --chat-upstream-port "$CHAT_PORT" \
      --entity-upstream-host 127.0.0.1 \
      --entity-upstream-port "$ENTITY_PORT" \
      "${content_upstream_args[@]}" \
      --avatar-cdn-base-url "$MEDIA_AVATAR_CDN_BASE_URL" \
      --image-cdn-base-url "$MEDIA_IMAGE_CDN_BASE_URL" \
      --video-cdn-base-url "$MEDIA_VIDEO_CDN_BASE_URL"

  beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/healthz" "gateway" 30
}

beta_manual_start_notification_service() {
  echo "[app-beta-manual] starting notification-service beta on :$BETA_NOTIFICATION_PORT"
  beta_manual_start_process \
    "notification-service" \
    "$NOTIFICATION_LOG" \
    "$ROOT_DIR/quwoquan_service/services/notification-service" \
    env \
      APP_ENV=beta \
      CONFIG_ROOT="$BETA_SERVICE_CONFIG_ROOT" \
      NOTIFICATION_SERVICE_ADDR=":${BETA_NOTIFICATION_PORT}" \
      NOTIFICATION_MONGO_URI="mongodb://127.0.0.1:${BETA_MONGO_PORT}/?directConnection=true" \
      NOTIFICATION_MONGO_DATABASE=quwoquan_notification \
      NOTIFICATION_INTEGRATION_BASE_URL="$INTERNAL_GATEWAY_BASE_URL" \
      NOTIFICATION_INTEGRATION_TIMEOUT_MS=1500 \
      NOTIFICATION_USER_BASE_URL="$INTERNAL_GATEWAY_BASE_URL" \
      NOTIFICATION_REALTIME_BASE_URL="$INTERNAL_GATEWAY_BASE_URL" \
      NOTIFICATION_REDIS_ADDR="127.0.0.1:${BETA_REDIS_PORT}" \
      NOTIFICATION_REDIS_GENERAL_DB=1 \
      NOTIFICATION_REDIS_REALTIME_DB=4 \
      go run ./cmd/api

  beta_manual_wait_http_ok \
    "http://127.0.0.1:${BETA_NOTIFICATION_PORT}/healthz" \
    "notification-service" \
    90
}

beta_manual_start_media_runtime() {
  rm -rf "$MEDIA_DIR"
  mkdir -p "$MEDIA_DIR/media"
  case "$MEDIA_PREP_MODE" in
    copy)
      cp -R "$CANONICAL_SOURCE_MEDIA_ROOT/." "$MEDIA_DIR/media/"
      ;;
    symlink)
      while IFS= read -r source_child; do
        child_name="$(basename "$source_child")"
        ln -s "$source_child" "$MEDIA_DIR/media/$child_name"
      done < <(find "$CANONICAL_SOURCE_MEDIA_ROOT" -mindepth 1 -maxdepth 1 -type d | sort)
      ;;
  esac
  mkdir -p "$MEDIA_DIR/media/video"
  python3 - "$MEDIA_DIR" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
source = root / "media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
target = root / "media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
if not source.is_file():
    raise SystemExit(f"playable sample video missing: {source}")
target.write_bytes(source.read_bytes())
PY
  echo "[app-beta-manual] starting local media origin on :$MEDIA_ORIGIN_PORT"
  beta_manual_start_process \
    "media-origin" \
    "$MEDIA_LOG" \
    "$ROOT_DIR" \
    python3 quwoquan_ops/cli/lib/local_media_origin.py \
      --listen-host 127.0.0.1 \
      --listen-port "$MEDIA_ORIGIN_PORT" \
      --root-dir "$MEDIA_DIR" \
      --server-label app-beta-manual-media-origin
  beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png" "media origin current user avatar fixture" 30 || return 1
  beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png" "media origin friend avatar fixture" 30 || return 1
  beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png" "media origin group avatar fixture" 30 || return 1
  beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" "media origin post cover fixture" 30 || return 1
  beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/image/s/archived-image/post/fixture_post_photography_001/v1/cover.jpg" "media origin mixed-format post cover fixture" 30 || return 1
  beta_manual_wait_http_range_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" "media origin playable video range" 30 || return 1
  echo "[app-beta-manual] starting local media edge on :$MEDIA_PORT -> :$MEDIA_ORIGIN_PORT"
  beta_manual_start_process \
    "media-edge" \
    "$MEDIA_EDGE_LOG" \
    "$ROOT_DIR" \
    python3 quwoquan_ops/cli/lib/http_reverse_proxy.py \
      --listen-host 127.0.0.1 \
      --listen-port "$MEDIA_PROCESSOR_PORT" \
      --target-base-url "http://127.0.0.1:${MEDIA_ORIGIN_PORT}"
  beta_manual_wait_http_ok "${INTERNAL_MEDIA_BASE_URL}/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png" "media edge current user avatar fixture" 30 || return 1
  beta_manual_wait_http_ok "${INTERNAL_MEDIA_BASE_URL}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" "media edge post cover fixture" 30 || return 1
  beta_manual_wait_http_range_ok "${INTERNAL_MEDIA_BASE_URL}/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" "media edge playable video range" 30 || return 1
  if [[ "$DEVICE_KIND" == android_* && -n "$FLUTTER_DEVICE_ID" && -x "$(command -v adb 2>/dev/null || true)" ]]; then
    adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${GATEWAY_PORT}" "tcp:${GATEWAY_PORT}" >/dev/null 2>&1 || true
    adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${MEDIA_PORT}" "tcp:${MEDIA_PORT}" >/dev/null 2>&1 || true
    adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${MEDIA_ORIGIN_PORT}" "tcp:${MEDIA_ORIGIN_PORT}" >/dev/null 2>&1 || true
    ADB_REVERSE_ENABLED=1
  fi
}

beta_manual_start_release_media_runtime() {
  # ship apply is the only writer of this directory.  Do not seed, copy, or
  # erase it here: doing so would replace an immutable release with fixtures.
  mkdir -p "$MEDIA_DIR"
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
  local listen_host="127.0.0.1"
  if [[ "$CONTENT_RELEASE_ONLY" == "1" ]]; then
    # Caddy is containerized; it reaches this local service through the host
    # gateway rather than the host loopback device.
    listen_host="0.0.0.0"
  fi
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
      ENTITY_REDIS_ADDR="127.0.0.1:${BETA_REDIS_PORT}" \
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
  echo "[app-beta-manual] content release slice is ready."
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

if [[ "$CONTENT_RELEASE_ONLY" == "1" ]]; then
  beta_manual_ensure_port_available "$GATEWAY_PORT" "gateway"
  beta_manual_ensure_port_available "$CONTENT_PORT" "content-service"
  beta_manual_ensure_port_available "$USER_PORT" "user-service"
  beta_manual_ensure_port_available "$BETA_OBJECT_STORAGE_EDGE_PORT" "object-storage"
  beta_manual_ensure_port_available "$ENTITY_PORT" "entity-service"
  beta_manual_ensure_port_available "$MEDIA_PORT" "media-edge"
  beta_manual_ensure_port_available "$MEDIA_PROCESSOR_PORT" "media-edge-upstream"
  beta_manual_ensure_port_available "$MEDIA_ORIGIN_PORT" "media-origin"
  echo "[app-beta-manual] starting the Beta Content/Notification release slice"
  beta_manual_start_content_release_stack || {
    echo "content release slice failed to become ready" >&2
    exit 1
  }
  exit 0
fi

if [[ "$START_ASSISTANT" == "1" ]]; then
  beta_manual_ensure_port_available "$ASSISTANT_PORT" "assistant-service"
fi
beta_manual_ensure_port_available "$CHAT_PORT" "chat-service"
beta_manual_ensure_port_available "$GATEWAY_PORT" "gateway"
beta_manual_ensure_port_available "$CONTENT_PORT" "content-service"
beta_manual_ensure_port_available "$BETA_NOTIFICATION_PORT" "notification-service"
beta_manual_ensure_port_available "$BETA_FIXTURE_GATEWAY_PORT" "fixture-gateway"
beta_manual_ensure_port_available "$BETA_OBJECT_STORAGE_EDGE_PORT" "object-storage"
beta_manual_ensure_port_available "$MEDIA_PORT" "media-edge"
beta_manual_ensure_port_available "$MEDIA_PROCESSOR_PORT" "media-edge-upstream"
beta_manual_ensure_port_available "$MEDIA_ORIGIN_PORT" "media-origin"

echo "[app-beta-manual] logs: $LOG_DIR"
if [[ "$START_ASSISTANT" == "1" ]]; then
  echo "[app-beta-manual] model: ${ASSISTANT_BETA_MODEL_REF:-unknown} (${ASSISTANT_MODEL_BASE_URL})"
else
  echo "[app-beta-manual] assistant-service disabled for content-only validation"
fi
echo "[app-beta-manual] verify mode: $VERIFY_MODE"
echo "[app-beta-manual] media mode: $MEDIA_PREP_MODE"
if [[ "$VERIFY_MODE" == "full" ]]; then
  python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/gate/verify_avatar_user_pool_consistency.py >/dev/null
else
  echo "[app-beta-manual] fast mode: skip full shared-pool consistency verification"
fi
beta_manual_start_media_runtime || {
  echo "media runtime failed to become ready" >&2
  echo "media edge log: $MEDIA_EDGE_LOG" >&2
  echo "media origin log: $MEDIA_LOG" >&2
  exit 1
}
beta_manual_ensure_data_plane || {
  echo "real beta content data plane must be ready before beta services start" >&2
  exit 1
}
if [[ "$START_ASSISTANT" == "1" ]]; then
  echo "[app-beta-manual] starting assistant-service beta on :$ASSISTANT_PORT"
  beta_manual_start_process \
    "assistant-service" \
    "$ASSISTANT_LOG" \
    "$ASSISTANT_SERVICE_DIR" \
    env \
      APP_ENV=beta \
      ASSISTANT_SERVICE_ADDR=":${ASSISTANT_PORT}" \
      POSTGRES_DSN="$BETA_POSTGRES_DSN" \
      MONGODB_URI="$CHAT_MONGO_URI" \
      MONGODB_DATABASE="quwoquan_assistant" \
      REDIS_GENERAL_ADDR="$CHAT_REDIS_ADDR" \
      REDIS_REC_ADDR="$CHAT_REDIS_ADDR" \
      ASSISTANT_SCENARIO_SEED_REFS="$ASSISTANT_SEED_REFS" \
      ASSISTANT_MODEL_PROVIDER="$ASSISTANT_MODEL_PROVIDER" \
      ASSISTANT_MODEL_BASE_URL="$ASSISTANT_MODEL_BASE_URL" \
      ASSISTANT_MODEL_MODEL="$ASSISTANT_MODEL_MODEL" \
      ASSISTANT_MODEL_API_KEY_ENV="$ASSISTANT_MODEL_API_KEY_ENV" \
      ASSISTANT_BETA_RESOLVED_MODEL_API_KEY="$ASSISTANT_BETA_RESOLVED_MODEL_API_KEY" \
      go run ./cmd/api

  beta_manual_wait_http_ok "http://127.0.0.1:${ASSISTANT_PORT}/healthz" "assistant-service" 60 || {
    echo "assistant log: $ASSISTANT_LOG" >&2
    echo "gateway log: $GATEWAY_LOG" >&2
    exit 1
  }
fi

echo "[app-beta-manual] seeding local chat fixture db refs: $CHAT_SEED_REFS"
IFS=',' read -r -a CHAT_SEED_REF_ARRAY <<< "$CHAT_SEED_REFS"
CHAT_SEED_ARGS=()
for seed_ref in "${CHAT_SEED_REF_ARRAY[@]}"; do
  if [[ -n "${seed_ref// }" ]]; then
    CHAT_SEED_ARGS+=(--seed-ref "$seed_ref")
  fi
done
mkdir -p "$(dirname "$CHAT_SEED_LOG")"
(
  cd "$CHAT_SERVICE_DIR"
  python3 "$BETA_MANUAL_RUNTIME_LOG_PROCESS" \
    --log-file "$CHAT_SEED_LOG" \
    --event "chat-seed" \
    -- go run ./cmd/seed-fixture \
      --mongo-uri "$CHAT_MONGO_URI" \
      --database "$CHAT_MONGO_DATABASE" \
      "${CHAT_SEED_ARGS[@]}"
) || {
  echo "chat seed log: $CHAT_SEED_LOG" >&2
  exit 1
}

echo "[app-beta-manual] starting chat-service beta on :$CHAT_PORT"
beta_manual_start_process \
  "chat-service" \
  "$CHAT_LOG" \
  "$CHAT_SERVICE_DIR" \
  env \
    APP_ENV=beta \
    CHAT_SERVICE_ADDR=":${CHAT_PORT}" \
    MONGO_URI="$CHAT_MONGO_URI" \
    MONGO_DATABASE="$CHAT_MONGO_DATABASE" \
    REDIS_ADDR="$CHAT_REDIS_ADDR" \
    CHAT_GROUP_AVATAR_CDN_BASE_URL="$MEDIA_AVATAR_CDN_BASE_URL" \
    CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT="$MEDIA_DIR" \
    USER_SERVICE_BASE_URL="$INTERNAL_GATEWAY_BASE_URL" \
    CIRCLE_SERVICE_BASE_URL="$INTERNAL_GATEWAY_BASE_URL" \
    CONTENT_SERVICE_BASE_URL="$INTERNAL_GATEWAY_BASE_URL" \
    RELIABLE_TASK_CATALOG_PATH="$ROOT_DIR/quwoquan_service/runtime/reliabletask/resources/module_catalog.yaml" \
    RELIABLE_TASK_RETENTION_POLICY_PATH="$ROOT_DIR/quwoquan_service/runtime/reliabletask/resources/retention_policy.yaml" \
    go run ./cmd/api

beta_manual_wait_http_ok "http://127.0.0.1:${CHAT_PORT}/healthz" "chat-service" 60 || {
  echo "chat log: $CHAT_LOG" >&2
  echo "chat seed log: $CHAT_SEED_LOG" >&2
  exit 1
}

beta_manual_start_entity_service || {
  echo "entity-service log: $ENTITY_LOG" >&2
  exit 1
}

beta_manual_start_fixture_gateway || {
  echo "gateway log: $GATEWAY_LOG" >&2
  exit 1
}
if [[ "$START_ASSISTANT" == "1" ]]; then
  beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/assistant/skill-subscriptions" "assistant route" 60 || { echo "assistant log: $ASSISTANT_LOG" >&2; echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
fi
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/config/app" "app config fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/content/feed" "content fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/chat/inbox" "chat inbox route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/chat/contacts" "chat contacts route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/chat/conversations" "chat conversations route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
python3 - "$BETA_FIXTURE_GATEWAY_PORT" <<'PY' || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

port = sys.argv[1]
req = Request(
    f"http://127.0.0.1:{port}/user/sync",
    data=json.dumps({"afterSeq": 0, "limit": 1}).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "X-Client-User-Id": "fixture_user_current",
    },
    method="POST",
)
try:
    with urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise SystemExit(f"user sync route unhealthy: {resp.status}")
except HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace").strip()
    raise SystemExit(f"user sync route unhealthy: HTTP {exc.code}: {detail[:500]}") from exc
PY
beta_manual_start_notification_service || {
  echo "notification log: $NOTIFICATION_LOG" >&2
  exit 1
}
beta_manual_start_tls_proxy
beta_manual_wait_https_ok "$PUBLIC_API_HOST" "$GATEWAY_PORT" "/healthz" "gateway public health" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_ensure_filter_catalog_release || {
  echo "filter catalog release bootstrap failed" >&2
  exit 1
}
beta_manual_wait_https_ok "$PUBLIC_API_HOST" "$GATEWAY_PORT" "/legal/user-agreement" "legal static user agreement" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_verify_legal_document "$PUBLIC_API_HOST" "$GATEWAY_PORT" "/legal/user-agreement" "趣我圈用户协议" || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_verify_legal_document "$PUBLIC_API_HOST" "$GATEWAY_PORT" "/legal/privacy-policy" "趣我圈隐私政策" || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_https_ok "$PUBLIC_IMAGE_HOST" "$MEDIA_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" "public media image route" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_https_range_ok "$PUBLIC_VIDEO_HOST" "$MEDIA_PORT" "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" "public media video route" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_https_ok "$PUBLIC_AVATAR_HOST" "$MEDIA_PORT" "/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png" "public media avatar route" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/circles" "circle fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/circles/fixture_circle_photo/feed" "circle feed fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/user/profile" "user fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/me" "current user fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/user/persona/personas/active" "active persona fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/user/settings/appearance" "appearance fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/content/profile-subjects/fixture_user_current/posts" "profile posts fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/users/fixture_user_current/works" "profile works fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/users/fixture_user_current/circles" "profile circles fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/user/sub-accounts/fixture_user_current/relationship/capability" "relationship capability fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/homepages/search" "entity fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/integration/external_integration/locations/pois" "integration fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/content/feed/intersections?limit=4&channel=recommend" "feed intersections fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/rtc/calls" "rtc fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }

python3 - "$REPORT" "$MANIFEST" "$GATEWAY_BASE_URL" "$ASSISTANT_PORT" "$CHAT_PORT" "$DEVICE_KIND" "$LOCAL_PUBLIC_HOST" "$MEDIA_AVATAR_CDN_BASE_URL" "$MEDIA_IMAGE_CDN_BASE_URL" "$MEDIA_VIDEO_CDN_BASE_URL" "$MEDIA_UPLOAD_BASE_URL" "http://127.0.0.1:${MEDIA_ORIGIN_PORT}" "$ADB_REVERSE_ENABLED" "$RESTARTED_FROM_PREVIOUS" "$FLUTTER_DEVICE_ID" "$VERIFY_MODE" "$MEDIA_PREP_MODE" "$START_ASSISTANT" <<'PY'
import json
import sys
from pathlib import Path

(
    report_path,
    manifest_path,
    gateway,
    assistant_port,
    chat_port,
    device_kind,
    local_public_host,
    avatar_cdn,
    image_cdn,
    video_cdn,
    upload_base,
    media_origin,
    adb_reverse,
    restarted_from_previous,
    flutter_device_id,
    seed_verify_mode,
    media_prep_mode,
    assistant_enabled,
) = sys.argv[1:19]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
checked_routes = [
    "/healthz",
    "/config/app",
    "/content/feed",
    "/chat/inbox",
    "/chat/contacts",
    "/chat/conversations",
    "/user/sync",
    "/circles",
    "/circles/fixture_circle_photo/feed",
    "/user/profile",
    "/me",
    "/user/persona/personas/active",
    "/user/settings/appearance",
    "/content/profile-subjects/fixture_user_current/posts",
    "/users/fixture_user_current/works",
    "/users/fixture_user_current/circles",
    "/user/sub-accounts/fixture_user_current/relationship/capability",
    "/homepages/search",
    "/integration/external_integration/locations/pois",
    "/content/feed/intersections?limit=4&channel=recommend",
    "/rtc/calls",
]
if assistant_enabled == "1":
    checked_routes.insert(1, "/assistant/skill-subscriptions")
report = {
    "status": "ready",
    "mode": "manual-beta",
    "serviceMode": "single-stack",
    "appRuntimeEnv": "beta",
    "composition": "production_remote",
    "flutterDeviceId": flutter_device_id,
    "gatewayBaseUrl": gateway,
    "deviceKind": device_kind,
    "localPublicHost": local_public_host,
    "avatarCdnBaseUrl": avatar_cdn,
    "imageCdnBaseUrl": image_cdn,
    "videoCdnBaseUrl": video_cdn,
    "uploadBaseUrl": upload_base,
    "mediaOriginBaseUrl": media_origin,
    "seedVerifyMode": seed_verify_mode,
    "mediaPrepMode": media_prep_mode,
    "adbReverseEnabled": adb_reverse == "1",
    "restartedFromPrevious": restarted_from_previous == "1",
    "assistantEnabled": assistant_enabled == "1",
    "assistantServiceUrl": (
        f"http://127.0.0.1:{assistant_port}"
        if assistant_enabled == "1"
        else None
    ),
    "chatServiceUrl": f"http://127.0.0.1:{chat_port}",
    "manifest": str(Path(manifest_path)),
    "checkedRoutes": checked_routes,
    "checkedMediaUrls": [
        f"{avatar_cdn.rstrip('/')}/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png",
        f"{avatar_cdn.rstrip('/')}/media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png",
        f"{avatar_cdn.rstrip('/')}/media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
        f"{image_cdn.rstrip('/')}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
        f"{video_cdn.rstrip('/')}/media/video/s/video-primary-0001/post/video-content-0001/source.mp4",
    ],
    "seedRefs": {
        item["domain"]: item["refs"]
        for item in manifest.get("seedRefs", [])
    },
}
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[app-beta-manual] beta environment is ready."
echo "[app-beta-manual] report: $REPORT"
echo "[app-beta-manual] APP_RUNTIME_ENV=beta production Remote composition CLOUD_GATEWAY_BASE_URL=$GATEWAY_BASE_URL APP_CURRENT_USER_ID=$APP_CURRENT_USER_ID"

if [[ "$SKIP_APP" == "1" ]]; then
  echo "[app-beta-manual] --skip-app set; beta cloud stack keeps running until Ctrl-C."
  if [[ "$START_ASSISTANT" == "1" ]]; then
    beta_manual_wait_until_stopped assistant-service chat-service notification-service gateway media-static
  else
    beta_manual_wait_until_stopped chat-service notification-service gateway media-static
  fi
  exit 0
fi

echo "[app-beta-manual] starting Flutter app on device: $FLUTTER_DEVICE_ID"
bash "$ROOT_DIR/quwoquan_app/scripts/device/start_app_instance.sh" \
  --env beta \
  --device-id "$FLUTTER_DEVICE_ID" \
  --gateway-base-url "$GATEWAY_BASE_URL" \
  --legal-base-url "$GATEWAY_BASE_URL/legal" \
  --media-avatar-base-url "$MEDIA_AVATAR_CDN_BASE_URL" \
  --media-image-base-url "$MEDIA_IMAGE_CDN_BASE_URL" \
  --media-video-base-url "$MEDIA_VIDEO_CDN_BASE_URL" \
  --media-upload-base-url "$MEDIA_UPLOAD_BASE_URL" \
  --current-user-id "$APP_CURRENT_USER_ID" \
  --instance-namespace "$INSTANCE_NAMESPACE" \
  --service-mode single-stack
