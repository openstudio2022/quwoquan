#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"
ASSISTANT_SERVICE_DIR="$ROOT_DIR/quwoquan_service/services/assistant-service"
CHAT_SERVICE_DIR="$ROOT_DIR/quwoquan_service/services/chat-service"
LOG_DIR="$ROOT_DIR/.qwq_output/env/beta/local/beta-local"
MANIFEST="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/app_beta_seed_manifest.json"

eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile beta-local --format shell-defaults)"
eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile gamma-local --format shell-defaults)"

ASSISTANT_PORT="${ASSISTANT_PORT}"
CHAT_PORT="${CHAT_PORT}"
GATEWAY_PORT="${GATEWAY_PORT}"
PRODUCT_OPS_PORT="${PRODUCT_OPS_PORT}"
MEDIA_PORT="${MEDIA_PORT}"
MEDIA_ORIGIN_PORT="${MEDIA_ORIGIN_PORT}"
CONTENT_PORT="${CONTENT_PORT}"
PRODUCT_OPS_SERVICE_PORT="${PRODUCT_OPS_SERVICE_PORT}"
MEDIA_PROCESSOR_PORT="${MEDIA_PROCESSOR_PORT}"
PUBLIC_API_HOST="beta-api.quwoquan-env.test"
PUBLIC_PRODUCT_OPS_HOST="beta-product-ops.quwoquan-env.test"
PUBLIC_AVATAR_HOST="beta-avatar.quwoquan-env.test"
PUBLIC_IMAGE_HOST="beta-image.quwoquan-env.test"
PUBLIC_VIDEO_HOST="beta-video.quwoquan-env.test"
PUBLIC_UPLOAD_HOST="beta-upload.quwoquan-env.test"
LOCAL_API_HOST="beta-api.localhost"
LOCAL_PRODUCT_OPS_HOST="beta-product-ops.localhost"
LOCAL_AVATAR_HOST="beta-avatar.localhost"
LOCAL_IMAGE_HOST="beta-image.localhost"
LOCAL_VIDEO_HOST="beta-video.localhost"
LOCAL_UPLOAD_HOST="beta-upload.localhost"
CHAT_SEED_REFS="${CHAT_SEED_REFS:-chat_core,chat_settings_core,chat_contacts_core,chat_group_flow_core}"
CHAT_MONGO_URI="${CHAT_MONGO_URI:-mongodb://localhost:27017/?directConnection=true}"
CHAT_MONGO_DATABASE="${CHAT_MONGO_DATABASE:-quwoquan_chat_local}"
CHAT_REDIS_ADDR="${CHAT_REDIS_ADDR:-localhost:6379}"
LOCAL_GAMMA_COMPOSE_FILE="$ROOT_DIR/quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
LOCAL_GAMMA_COMPOSE_PROJECT_NAME="${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:-quwoquan_service}"
LOCAL_GAMMA_MONGO_PORT="${LOCAL_GAMMA_MONGO_PORT}"
LOCAL_GAMMA_REDIS_PORT="${LOCAL_GAMMA_REDIS_PORT}"
GATEWAY_BASE_URL_EXPLICIT=0
if [[ -n "${GATEWAY_BASE_URL:-}" ]]; then
  GATEWAY_BASE_URL_EXPLICIT=1
else
  GATEWAY_BASE_URL="https://${PUBLIC_API_HOST}:${GATEWAY_PORT}"
fi
LOCAL_PUBLIC_HOST="${LOCAL_PUBLIC_HOST:-}"
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-}"
INTERNAL_GATEWAY_BASE_URL="http://127.0.0.1:${CONTENT_PORT}"
INTERNAL_MEDIA_BASE_URL="http://127.0.0.1:${MEDIA_PROCESSOR_PORT}"
INTERNAL_PRODUCT_OPS_BASE_URL="http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}"
APP_CURRENT_USER_ID="${APP_CURRENT_USER_ID:-fixture_user_current}"
ASSISTANT_SEED_REFS="${ASSISTANT_SEED_REFS:-assistant_p0_core}"
FLUTTER_DEVICE_ID="${FLUTTER_DEVICE_ID:-}"
DEV_UP_HELPER="$ROOT_DIR/quwoquan_ops/cli/lib/dev_up.py"
SKIP_APP=0
KILL_EXISTING=1
RESTART_STACK=1
CLEAN_ENV=0
VERIFY_MODE="${BETA_SEED_VERIFY_MODE:-fast}"
MEDIA_PREP_MODE="${BETA_MEDIA_PREP_MODE:-symlink}"

BETA_MANUAL_LABEL="app-beta-manual"
BETA_MANUAL_STACK_NAME="beta-local"
BETA_MANUAL_LOG_DIR="$LOG_DIR"
INSTANCE_NAMESPACE="${INSTANCE_NAMESPACE:-beta-local}"
BETA_MANUAL_OWNER_ID="${BETA_MANUAL_STACK_NAME}-$$-$(date +%s)"
export BETA_MANUAL_OWNER_ID
source "$ROOT_DIR/quwoquan_ops/cli/lib/beta_manual_lifecycle.sh"
TLS_PROXY_NAME="quwoquan_beta_tls_proxy"
TLS_PROXY_CADDYFILE="$LOG_DIR/beta-public-plane.Caddyfile"
TLS_PROXY_DATA_DIR="$LOG_DIR/caddy/data"
TLS_PROXY_CONFIG_DIR="$LOG_DIR/caddy/config"
CONTAINER_RUNTIME=""
CONTAINER_HOST_ALIAS=""

usage() {
  cat <<EOF
Usage:
  scripts/start_app_beta_manual.sh [options]

Default:
  Restart the local beta cloud stack, then start the Flutter app.

Options:
  --device-id <id>           Flutter device id for manual beta run.
  --gateway-base-url <url>   Gateway URL injected into Flutter app.
                             iOS simulator default: http://127.0.0.1:${GATEWAY_PORT}
                             Android emulator usually: http://10.0.2.2:${GATEWAY_PORT}
  --local-public-host <host>  Host visible from the App device for gateway/media.
  --media-base-url <url>      Media CDN/upload base URL injected into Flutter app.
                             Defaults to http://<local-public-host>:${MEDIA_PORT} (media-edge).
  --seed-verify <fast|full>   Seed verification mode before start (default: ${VERIFY_MODE}).
  --media-mode <symlink|copy> Media root preparation mode (default: ${MEDIA_PREP_MODE}).
  --full-matrix              Equivalent to --seed-verify full --media-mode copy.
  --skip-app                 Start/check beta cloud stack only; do not start Flutter.
  --restart                  Stop a managed previous stack before starting (default on).
  --clean-env                Remove runtime pid/env state before starting.
  --kill-existing            Reclaim beta ports by killing listeners (default on).
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
    --media-base-url)
      MEDIA_AVATAR_CDN_BASE_URL="${2:-}"
      MEDIA_IMAGE_CDN_BASE_URL="${2:-}"
      MEDIA_VIDEO_CDN_BASE_URL="${2:-}"
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
    --kill-existing)
      KILL_EXISTING=1
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

beta_manual_compose_up_chat_backing_services() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "chat backing services unavailable and docker is not installed" >&2
    return 1
  fi
  if [[ ! -f "$LOCAL_GAMMA_COMPOSE_FILE" ]]; then
    echo "local gamma compose file missing: $LOCAL_GAMMA_COMPOSE_FILE" >&2
    return 1
  fi
  echo "[app-beta-manual] starting fallback mongodb/redis via local gamma compose"
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" -f "$LOCAL_GAMMA_COMPOSE_FILE" up -d mongodb mongo-init redis >/dev/null
}

beta_manual_ensure_docker_daemon() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker CLI unavailable; cannot start chat fallback services" >&2
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

beta_manual_ensure_chat_backing_services() {
  local default_mongo_uri="mongodb://localhost:27017/?directConnection=true"
  local default_redis_addr="localhost:6379"
  local effective_mongo_uri="$CHAT_MONGO_URI"
  local effective_redis_addr="$CHAT_REDIS_ADDR"

  if beta_manual_check_mongo "$effective_mongo_uri" && beta_manual_check_redis "$effective_redis_addr"; then
    return 0
  fi

  if [[ "$CHAT_MONGO_URI" != "$default_mongo_uri" || "$CHAT_REDIS_ADDR" != "$default_redis_addr" ]]; then
    if ! beta_manual_check_mongo "$effective_mongo_uri"; then
      echo "chat mongo unavailable: $effective_mongo_uri" >&2
    fi
    if ! beta_manual_check_redis "$effective_redis_addr"; then
      echo "chat redis unavailable: $effective_redis_addr" >&2
    fi
    return 1
  fi

  beta_manual_ensure_docker_daemon || return 1
  beta_manual_compose_up_chat_backing_services || return 1
  effective_mongo_uri="mongodb://127.0.0.1:${LOCAL_GAMMA_MONGO_PORT}/?directConnection=true"
  effective_redis_addr="127.0.0.1:${LOCAL_GAMMA_REDIS_PORT}"
  beta_manual_wait_mongo_ready "$effective_mongo_uri" "chat mongo fallback" 90 || return 1
  beta_manual_wait_redis_ready "$effective_redis_addr" "chat redis fallback" 90 || return 1
  CHAT_MONGO_URI="$effective_mongo_uri"
  CHAT_REDIS_ADDR="$effective_redis_addr"
  echo "[app-beta-manual] chat mongo fallback OK: $CHAT_MONGO_URI"
  echo "[app-beta-manual] chat redis fallback OK: $CHAT_REDIS_ADDR"
}

resolve_assistant_model_env() {
  python3 - <<'PY'
import os
import shlex
provider = os.environ.get("ASSISTANT_MODEL_PROVIDER", "deterministic").strip() or "deterministic"
base_url = os.environ.get("ASSISTANT_MODEL_BASE_URL", "").strip()
model_id = os.environ.get("ASSISTANT_MODEL_MODEL", "").strip()
api_key = os.environ.get("ASSISTANT_MODEL_API_KEY", "").strip()
if not api_key:
    api_key = os.environ.get("PERSONAL_ASSISTANT_MIMO_API_KEY", "").strip()
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

eval "$(resolve_assistant_model_env)"

if [[ "${ASSISTANT_MODEL_PROVIDER}" != "deterministic" && "${ASSISTANT_MODEL_PROVIDER}" != "fake" && -z "${ASSISTANT_BETA_RESOLVED_MODEL_API_KEY:-}" ]]; then
  echo "GATE_BLOCK: no assistant beta model key resolved from environment." >&2
  exit 2
fi

BETA_MANUAL_KILL_EXISTING="$KILL_EXISTING"
beta_manual_init
RESTARTED_FROM_PREVIOUS=0
if [[ -f "$BETA_MANUAL_STATE_DIR/stack.env" ]] || [[ -n "$(beta_manual_port_pids "$GATEWAY_PORT")" ]] || [[ -n "$(beta_manual_port_pids "$MEDIA_PORT")" ]] || [[ -n "$(beta_manual_port_pids "$ASSISTANT_PORT")" ]] || [[ -n "$(beta_manual_port_pids "$CHAT_PORT")" ]]; then
  RESTARTED_FROM_PREVIOUS=1
fi
ASSISTANT_LOG="$LOG_DIR/assistant-service-beta.log"
CHAT_LOG="$LOG_DIR/chat-service-beta.log"
CHAT_SEED_LOG="$LOG_DIR/chat-seed.log"
GATEWAY_LOG="$LOG_DIR/app-beta-gateway.log"
MEDIA_LOG="$LOG_DIR/app-beta-media.log"
MEDIA_DIR="$LOG_DIR/media"
SOURCE_MEDIA_ROOT="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
CANONICAL_SOURCE_MEDIA_ROOT="$SOURCE_MEDIA_ROOT"
if [[ -d "$SOURCE_MEDIA_ROOT/media" ]]; then
  CANONICAL_SOURCE_MEDIA_ROOT="$SOURCE_MEDIA_ROOT/media"
fi
REPORT="$LOG_DIR/app-beta-manual-report.json"

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
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-https://${PUBLIC_AVATAR_HOST}:${MEDIA_PORT}}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-https://${PUBLIC_IMAGE_HOST}:${MEDIA_PORT}}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-https://${PUBLIC_VIDEO_HOST}:${MEDIA_PORT}}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-https://${PUBLIC_UPLOAD_HOST}:${MEDIA_PORT}}"
if [[ "$DEVICE_KIND" == android_* ]]; then
  LOCAL_PUBLIC_HOST="$LOCAL_API_HOST"
  if [[ "$GATEWAY_BASE_URL_EXPLICIT" == "0" ]]; then
    GATEWAY_BASE_URL="https://${LOCAL_API_HOST}:${GATEWAY_PORT}"
  fi
  MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL/https:\/\/${PUBLIC_AVATAR_HOST}:https:\/\/${LOCAL_AVATAR_HOST}:}"
  MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL/https:\/\/${PUBLIC_IMAGE_HOST}:https:\/\/${LOCAL_IMAGE_HOST}:}"
  MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL/https:\/\/${PUBLIC_VIDEO_HOST}:https:\/\/${LOCAL_VIDEO_HOST}:}"
  MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL/https:\/\/${PUBLIC_UPLOAD_HOST}:https:\/\/${LOCAL_UPLOAD_HOST}:}"
fi

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
bash "$ROOT_DIR/quwoquan_service/scripts/runtime/build_service_env_package.sh" --service assistant-service --env beta >/dev/null

if [[ "$RESTART_STACK" == "1" || "$CLEAN_ENV" == "1" ]]; then
  echo "[app-beta-manual] restarting managed beta stack before launch"
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  elif command -v podman >/dev/null 2>&1; then
    podman rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  fi
  beta_manual_stop_stack "$CLEAN_ENV"
  beta_manual_init
fi

: >"$BETA_MANUAL_STATE_DIR/stack.env"
beta_manual_record_metadata "stack" "$BETA_MANUAL_STACK_NAME"
beta_manual_record_metadata "controller_pid" "$$"
beta_manual_record_metadata "owner_id" "$BETA_MANUAL_OWNER_ID"
beta_manual_record_metadata "assistant_port" "$ASSISTANT_PORT"
beta_manual_record_metadata "chat_port" "$CHAT_PORT"
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
  mkdir -p "$TLS_PROXY_DATA_DIR" "$TLS_PROXY_CONFIG_DIR"
  cat >"$TLS_PROXY_CADDYFILE" <<EOF
{
	admin off
	local_certs
}

(local_tls) {
	tls internal
}

(media_cors) {
	header {
		Access-Control-Allow-Origin "*"
		Access-Control-Allow-Methods "GET, HEAD, OPTIONS"
		Access-Control-Allow-Headers "*"
		Cross-Origin-Resource-Policy "cross-origin"
	}
}

${PUBLIC_API_HOST},
${LOCAL_API_HOST} {
	import local_tls
	reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
}

${PUBLIC_PRODUCT_OPS_HOST},
${LOCAL_PRODUCT_OPS_HOST} {
	import local_tls
	reverse_proxy ${CONTAINER_HOST_ALIAS}:${PRODUCT_OPS_SERVICE_PORT}
}

${PUBLIC_AVATAR_HOST},
${PUBLIC_IMAGE_HOST},
${PUBLIC_VIDEO_HOST},
${PUBLIC_UPLOAD_HOST},
${LOCAL_AVATAR_HOST},
${LOCAL_IMAGE_HOST},
${LOCAL_VIDEO_HOST},
${LOCAL_UPLOAD_HOST} {
	import local_tls
	import media_cors
	reverse_proxy ${CONTAINER_HOST_ALIAS}:${MEDIA_PROCESSOR_PORT}
}
EOF
}

beta_manual_stop_tls_proxy() {
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
    return 0
  fi
  if command -v podman >/dev/null 2>&1; then
    podman rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
  fi
}

beta_manual_start_tls_proxy() {
  beta_manual_prepare_tls_caddyfile
  beta_manual_stop_tls_proxy
  "$CONTAINER_RUNTIME" run -d \
    --name "$TLS_PROXY_NAME" \
    -v "$TLS_PROXY_CADDYFILE:/etc/caddy/Caddyfile:ro" \
    -v "$TLS_PROXY_DATA_DIR:/data" \
    -v "$TLS_PROXY_CONFIG_DIR:/config" \
    -p "${GATEWAY_PORT}:443" \
    -p "${PRODUCT_OPS_PORT}:443" \
    -p "${MEDIA_PORT}:443" \
    docker.io/library/caddy:2.8.4-alpine >/dev/null
}

beta_manual_wait_https_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local label="$4"
  local timeout="${5:-30}"
  local deadline=$((SECONDS + timeout))
  until curl -kfsS \
    --resolve "${host}:${port}:127.0.0.1" \
    "https://${host}:${port}${path}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "${label} unavailable: https://${host}:${port}${path}" >&2
      return 1
    fi
    sleep 0.5
  done
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
      curl -kfsS \
        --resolve "${host}:${port}:127.0.0.1" \
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

cleanup() {
  trap - EXIT INT TERM HUP TSTP
  beta_manual_stop_tls_proxy
  beta_manual_stop_stack "$CLEAN_ENV" "$BETA_MANUAL_OWNER_ID"
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM
trap 'cleanup; exit 129' HUP
trap 'cleanup; exit 148' TSTP

beta_manual_ensure_port_available "$ASSISTANT_PORT" "assistant-service"
beta_manual_ensure_port_available "$CHAT_PORT" "chat-service"
beta_manual_ensure_port_available "$GATEWAY_PORT" "gateway"
beta_manual_ensure_port_available "$CONTENT_PORT" "gateway-upstream"
beta_manual_ensure_port_available "$MEDIA_PORT" "media-edge"
beta_manual_ensure_port_available "$MEDIA_PROCESSOR_PORT" "media-edge-upstream"
beta_manual_ensure_port_available "$MEDIA_ORIGIN_PORT" "media-origin"

echo "[app-beta-manual] logs: $LOG_DIR"
echo "[app-beta-manual] model: ${ASSISTANT_BETA_MODEL_REF:-unknown} (${ASSISTANT_MODEL_BASE_URL})"
echo "[app-beta-manual] verify mode: $VERIFY_MODE"
echo "[app-beta-manual] media mode: $MEDIA_PREP_MODE"
if [[ "$VERIFY_MODE" == "full" ]]; then
  python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/gate/verify_avatar_user_pool_consistency.py >/dev/null
else
  echo "[app-beta-manual] fast mode: skip full shared-pool consistency verification"
fi
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
source = root / "media/video/s/archived-video/beta-sample.mp4"
target = root / "media/video/beta-sample.mp4"
if not source.is_file():
    raise SystemExit(f"playable sample video missing: {source}")
target.write_bytes(source.read_bytes())
PY
MEDIA_EDGE_LOG="$LOG_DIR/media-edge.log"
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
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png" "media origin current user avatar fixture" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png" "media origin friend avatar fixture" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png" "media origin group avatar fixture" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" "media origin post cover fixture" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/image/s/archived-image/post/fixture_post_photography_001/v1/cover.jpg" "media origin mixed-format post cover fixture" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_range_ok "http://127.0.0.1:${MEDIA_ORIGIN_PORT}/media/video/s/archived-video/beta-sample.mp4" "media origin playable video range" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
echo "[app-beta-manual] starting local media edge on :$MEDIA_PORT -> :$MEDIA_ORIGIN_PORT"
beta_manual_start_process \
  "media-edge" \
  "$MEDIA_EDGE_LOG" \
  "$ROOT_DIR" \
  python3 quwoquan_ops/cli/lib/http_reverse_proxy.py \
    --listen-host 127.0.0.1 \
    --listen-port "$MEDIA_PROCESSOR_PORT" \
    --target-base-url "http://127.0.0.1:${MEDIA_ORIGIN_PORT}"
beta_manual_wait_http_ok "${INTERNAL_MEDIA_BASE_URL}/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png" "media edge current user avatar fixture" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_MEDIA_BASE_URL}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" "media edge post cover fixture" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_range_ok "${INTERNAL_MEDIA_BASE_URL}/media/video/s/archived-video/beta-sample.mp4" "media edge playable video range" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
if [[ "$DEVICE_KIND" == android_* && -n "$FLUTTER_DEVICE_ID" && -x "$(command -v adb 2>/dev/null || true)" ]]; then
  adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${GATEWAY_PORT}" "tcp:${GATEWAY_PORT}" >/dev/null 2>&1 || true
  adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${MEDIA_PORT}" "tcp:${MEDIA_PORT}" >/dev/null 2>&1 || true
  adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${MEDIA_ORIGIN_PORT}" "tcp:${MEDIA_ORIGIN_PORT}" >/dev/null 2>&1 || true
  ADB_REVERSE_ENABLED=1
fi
echo "[app-beta-manual] starting assistant-service beta on :$ASSISTANT_PORT"
beta_manual_start_process \
  "assistant-service" \
  "$ASSISTANT_LOG" \
  "$ASSISTANT_SERVICE_DIR" \
  env \
    APP_ENV=beta \
    ASSISTANT_SERVICE_ADDR=":${ASSISTANT_PORT}" \
    ASSISTANT_SCENARIO_SEED_REFS="$ASSISTANT_SEED_REFS" \
    ASSISTANT_MODEL_PROVIDER="$ASSISTANT_MODEL_PROVIDER" \
    ASSISTANT_MODEL_BASE_URL="$ASSISTANT_MODEL_BASE_URL" \
    ASSISTANT_MODEL_MODEL="$ASSISTANT_MODEL_MODEL" \
    ASSISTANT_MODEL_API_KEY_ENV="$ASSISTANT_MODEL_API_KEY_ENV" \
    ASSISTANT_BETA_RESOLVED_MODEL_API_KEY="$ASSISTANT_BETA_RESOLVED_MODEL_API_KEY" \
    ALLOW_DETERMINISTIC_BETA="${ALLOW_DETERMINISTIC_BETA:-1}" \
    go run ./cmd/api

beta_manual_wait_http_ok "http://127.0.0.1:${ASSISTANT_PORT}/healthz" "assistant-service" 60 || {
  echo "assistant log: $ASSISTANT_LOG" >&2
  echo "gateway log: $GATEWAY_LOG" >&2
  exit 1
}

beta_manual_ensure_chat_backing_services || {
  echo "assistant log: $ASSISTANT_LOG" >&2
  exit 1
}

echo "[app-beta-manual] seeding local chat fixture db refs: $CHAT_SEED_REFS"
IFS=',' read -r -a CHAT_SEED_REF_ARRAY <<< "$CHAT_SEED_REFS"
CHAT_SEED_ARGS=()
for seed_ref in "${CHAT_SEED_REF_ARRAY[@]}"; do
  if [[ -n "${seed_ref// }" ]]; then
    CHAT_SEED_ARGS+=(--seed-ref "$seed_ref")
  fi
done
(
  cd "$CHAT_SERVICE_DIR"
  go run ./cmd/seed-fixture \
    --mongo-uri "$CHAT_MONGO_URI" \
    --database "$CHAT_MONGO_DATABASE" \
    "${CHAT_SEED_ARGS[@]}"
) >"$CHAT_SEED_LOG" 2>&1 || {
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
    RELIABLE_TASK_CATALOG_PATH="$ROOT_DIR/quwoquan_ops/environments/reliable_task_module_catalog.yaml" \
    RELIABLE_TASK_RETENTION_POLICY_PATH="$ROOT_DIR/quwoquan_ops/environments/reliable_task_retention_policy.yaml" \
    go run ./cmd/api

beta_manual_wait_http_ok "http://127.0.0.1:${CHAT_PORT}/healthz" "chat-service" 60 || {
  echo "chat log: $CHAT_LOG" >&2
  echo "chat seed log: $CHAT_SEED_LOG" >&2
  exit 1
}

echo "[app-beta-manual] starting unified local beta gateway on :$GATEWAY_PORT"
beta_manual_start_process \
  "gateway" \
  "$GATEWAY_LOG" \
  "$ROOT_DIR" \
  python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/smoke/dev_assistant_beta_gateway.py \
    --listen-host 127.0.0.1 \
    --listen-port "$CONTENT_PORT" \
    --assistant-upstream-host 127.0.0.1 \
    --assistant-upstream-port "$ASSISTANT_PORT" \
    --chat-upstream-host 127.0.0.1 \
    --chat-upstream-port "$CHAT_PORT" \
    --avatar-cdn-base-url "$MEDIA_AVATAR_CDN_BASE_URL" \
    --image-cdn-base-url "$MEDIA_IMAGE_CDN_BASE_URL" \
    --video-cdn-base-url "$MEDIA_VIDEO_CDN_BASE_URL"

beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/healthz" "gateway" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/assistant/skill-subscriptions" "assistant route" 60 || { echo "assistant log: $ASSISTANT_LOG" >&2; echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/config/app" "app config fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/content/feed" "content fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/chat/inbox" "chat inbox route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/chat/contacts" "chat contacts route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/chat/conversations" "chat conversations route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
python3 - "$CONTENT_PORT" <<'PY' || { echo "gateway log: $GATEWAY_LOG" >&2; echo "chat log: $CHAT_LOG" >&2; exit 1; }
import json
import sys
from urllib.request import Request, urlopen

port = sys.argv[1]
req = Request(
    f"http://127.0.0.1:{port}/v1/user/sync",
    data=json.dumps({"afterSeq": 0, "limit": 1}).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "X-Client-User-Id": "fixture_user_current",
    },
    method="POST",
)
with urlopen(req, timeout=30) as resp:
    if resp.status != 200:
        raise SystemExit(f"user sync route unhealthy: {resp.status}")
PY
beta_manual_start_tls_proxy
beta_manual_wait_https_ok "$PUBLIC_API_HOST" "$GATEWAY_PORT" "/healthz" "gateway public health" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_https_ok "$PUBLIC_IMAGE_HOST" "$MEDIA_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" "public media image route" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_https_range_ok "$PUBLIC_VIDEO_HOST" "$MEDIA_PORT" "/media/video/s/archived-video/beta-sample.mp4" "public media video route" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_https_ok "$PUBLIC_AVATAR_HOST" "$MEDIA_PORT" "/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png" "public media avatar route" 30 || { echo "media edge log: $MEDIA_EDGE_LOG" >&2; echo "media origin log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/circles" "circle fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/circles/fixture_circle_photo/feed" "circle feed fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/user/profile" "user fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/me" "current user fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/user/personas/active" "active persona fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/user/settings/appearance" "appearance fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/content/profile-subjects/fixture_user_current/posts" "profile posts fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/users/fixture_user_current/works" "profile works fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/users/fixture_user_current/circles" "profile circles fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/user/sub-accounts/fixture_user_current/relationship/capability" "relationship capability fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/entity/homepages" "entity fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/integration/locations/pois" "integration fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/app-messages" "notification fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/app-messages/unread-count" "notification unread-count route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/notifications/unread-count" "notification aggregate unread-count route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/content/feed/intersections?limit=4&channel=recommend" "feed intersections fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "${INTERNAL_GATEWAY_BASE_URL}/v1/rtc/calls" "rtc fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }

python3 - "$REPORT" "$MANIFEST" "$GATEWAY_BASE_URL" "$ASSISTANT_PORT" "$CHAT_PORT" "$DEVICE_KIND" "$LOCAL_PUBLIC_HOST" "$MEDIA_AVATAR_CDN_BASE_URL" "$MEDIA_IMAGE_CDN_BASE_URL" "$MEDIA_VIDEO_CDN_BASE_URL" "$MEDIA_UPLOAD_BASE_URL" "http://127.0.0.1:${MEDIA_ORIGIN_PORT}" "$ADB_REVERSE_ENABLED" "$RESTARTED_FROM_PREVIOUS" "$FLUTTER_DEVICE_ID" "$VERIFY_MODE" "$MEDIA_PREP_MODE" <<'PY'
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
) = sys.argv[1:18]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
report = {
    "status": "ready",
    "mode": "manual-beta",
    "serviceMode": "single-stack",
    "appRuntimeEnv": "beta",
    "appDataSource": "remote",
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
    "assistantServiceUrl": f"http://127.0.0.1:{assistant_port}",
    "chatServiceUrl": f"http://127.0.0.1:{chat_port}",
    "manifest": str(Path(manifest_path)),
    "checkedRoutes": [
        "/healthz",
        "/v1/assistant/skill-subscriptions",
        "/v1/config/app",
        "/v1/content/feed",
        "/v1/chat/inbox",
        "/v1/chat/contacts",
        "/v1/chat/conversations",
        "/v1/user/sync",
        "/v1/circles",
        "/v1/circles/fixture_circle_photo/feed",
        "/v1/user/profile",
        "/v1/me",
        "/v1/user/personas/active",
        "/v1/user/settings/appearance",
        "/v1/content/profile-subjects/fixture_user_current/posts",
        "/v1/users/fixture_user_current/works",
        "/v1/users/fixture_user_current/circles",
        "/v1/user/sub-accounts/fixture_user_current/relationship/capability",
        "/v1/entity/homepages",
        "/v1/integration/locations/pois",
        "/v1/app-messages",
        "/v1/app-messages/unread-count",
        "/v1/notifications/unread-count",
        "/v1/content/feed/intersections?limit=4&channel=recommend",
        "/v1/rtc/calls",
    ],
    "checkedMediaUrls": [
        f"{avatar_cdn.rstrip('/')}/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png",
        f"{avatar_cdn.rstrip('/')}/media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png",
        f"{avatar_cdn.rstrip('/')}/media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
        f"{image_cdn.rstrip('/')}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
        f"{video_cdn.rstrip('/')}/media/video/beta-sample.mp4",
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
echo "[app-beta-manual] APP_RUNTIME_ENV=beta APP_DATA_SOURCE=remote CLOUD_GATEWAY_BASE_URL=$GATEWAY_BASE_URL APP_CURRENT_USER_ID=$APP_CURRENT_USER_ID"

if [[ "$SKIP_APP" == "1" ]]; then
  echo "[app-beta-manual] --skip-app set; beta cloud stack keeps running until Ctrl-C."
  beta_manual_wait_until_stopped assistant-service chat-service gateway media-static
  exit 0
fi

echo "[app-beta-manual] starting Flutter app on device: $FLUTTER_DEVICE_ID"
if [[ "$DEVICE_KIND" == android_* ]]; then
  if [[ ! -f "$TLS_PROXY_DATA_DIR/caddy/pki/authorities/local/root.crt" ]]; then
    echo "GATE_BLOCK: beta local Android debug CA missing: $TLS_PROXY_DATA_DIR/caddy/pki/authorities/local/root.crt" >&2
    exit 2
  fi
  export QWQ_ANDROID_LOCAL_ENV_CA_PATH="$TLS_PROXY_DATA_DIR/caddy/pki/authorities/local/root.crt"
  export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1
fi
bash "$ROOT_DIR/quwoquan_app/scripts/device/start_app_instance.sh" \
  --env beta \
  --device-id "$FLUTTER_DEVICE_ID" \
  --gateway-base-url "$GATEWAY_BASE_URL" \
  --media-avatar-base-url "$MEDIA_AVATAR_CDN_BASE_URL" \
  --media-image-base-url "$MEDIA_IMAGE_CDN_BASE_URL" \
  --media-video-base-url "$MEDIA_VIDEO_CDN_BASE_URL" \
  --media-upload-base-url "$MEDIA_UPLOAD_BASE_URL" \
  --current-user-id "$APP_CURRENT_USER_ID" \
  --instance-namespace "$INSTANCE_NAMESPACE" \
  --service-mode single-stack
