#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/quwoquan_service/docker-compose.gamma-local.yaml"
CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-local-gamma-v1}"
IMAGE_VERSION="${LOCAL_GAMMA_IMAGE_VERSION:-0.0.1}"
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-http://127.0.0.1:18080}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-https://gamma-product-ops.quwoquan-env.test}"
MEDIA_BASE_URL="${LOCAL_GAMMA_MEDIA_BASE_URL:-http://127.0.0.1:18080}"
DOCKER_LIBRARY_PREFIX="${LOCAL_GAMMA_DOCKER_LIBRARY_PREFIX:-docker.m.daocloud.io/library}"

library_image() {
  local image="$1"
  printf '%s/%s' "${DOCKER_LIBRARY_PREFIX%/}" "$image"
}

export LOCAL_GAMMA_POSTGRES_IMAGE="${LOCAL_GAMMA_POSTGRES_IMAGE:-$(library_image postgres:16-alpine)}"
export LOCAL_GAMMA_MONGO_IMAGE="${LOCAL_GAMMA_MONGO_IMAGE:-$(library_image mongo:7-jammy)}"
export LOCAL_GAMMA_REDIS_IMAGE="${LOCAL_GAMMA_REDIS_IMAGE:-$(library_image redis:7.2-alpine)}"
export LOCAL_GAMMA_GO_BOOKWORM_IMAGE="${LOCAL_GAMMA_GO_BOOKWORM_IMAGE:-$(library_image golang:1.24-bookworm)}"
export LOCAL_GAMMA_CADDY_IMAGE="${LOCAL_GAMMA_CADDY_IMAGE:-$(library_image caddy:2.8-alpine)}"
export LOCAL_GAMMA_GO_ALPINE_BASE_IMAGE="${LOCAL_GAMMA_GO_ALPINE_BASE_IMAGE:-$(library_image golang:1.24.3-alpine)}"
export LOCAL_GAMMA_ALPINE_BASE_IMAGE="${LOCAL_GAMMA_ALPINE_BASE_IMAGE:-$(library_image alpine:3.19)}"
export LOCAL_GAMMA_PYTHON_BASE_IMAGE="${LOCAL_GAMMA_PYTHON_BASE_IMAGE:-$(library_image python:3.11-slim)}"

skip_build=0
skip_up=0
print_env=0
down=0
tunnel_pid_file="$ROOT/artifacts/local-gamma/colima-tunnels.pids"

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

  local http_port="${LOCAL_GAMMA_HTTP_PORT:-18080}"
  local product_ops_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-18086}"
  local ssh_config="$ROOT/artifacts/local-gamma/colima-ssh-config"
  mkdir -p "$ROOT/artifacts/local-gamma"
  stop_colima_tunnels
  colima ssh-config > "$ssh_config"
  : > "$tunnel_pid_file"
  for port in "$http_port" "$product_ops_port"; do
    if host_port_open "$port"; then
      continue
    fi
    ssh -F "$ssh_config" -N -L "127.0.0.1:${port}:127.0.0.1:${port}" colima \
      > "$ROOT/artifacts/local-gamma/colima-tunnel-${port}.log" 2>&1 &
    echo "$!" >> "$tunnel_pid_file"
  done
  sleep 2
}

usage() {
  cat <<'USAGE'
Usage: scripts/start_local_gamma_mirror.sh [options]

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

prepare_config_root() {
  local out="$ROOT/artifacts/local-gamma/config-root"
  rm -rf "$out"
  mkdir -p \
    "$out/configs/content-service/default" \
    "$out/configs/content-service/gamma" \
    "$out/releases/config/content-service" \
    "$out/configs/chat-service/default" \
    "$out/configs/chat-service/gamma" \
    "$out/releases/config/chat-service" \
    "$out/configs/user-service/default" \
    "$out/configs/user-service/gamma" \
    "$out/releases/config/user-service" \
    "$out/configs/assistant-service/default" \
    "$out/configs/assistant-service/gamma" \
    "$out/releases/config/assistant-service" \
    "$out/deploy/shared" \
    "$out/configs/product-ops-service/default" \
    "$out/configs/product-ops-service/gamma" \
    "$out/releases/config/product-ops-service" \
    "$out/configs/recommendation-service/default" \
    "$out/configs/recommendation-service/gamma" \
    "$out/releases/config/recommendation-service"
  cp "$ROOT/quwoquan_service/services/content-service/configs/default/config.yaml" "$out/configs/content-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/content-service/configs/gamma/config.yaml" "$out/configs/content-service/gamma/config.yaml"
  cp "$ROOT/quwoquan_service/services/chat-service/configs/default/config.yaml" "$out/configs/chat-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/chat-service/configs/gamma/config.yaml" "$out/configs/chat-service/gamma/config.yaml"
  cp "$ROOT/quwoquan_service/services/user-service/configs/default/config.yaml" "$out/configs/user-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/user-service/configs/gamma/config.yaml" "$out/configs/user-service/gamma/config.yaml"
  cp "$ROOT/quwoquan_service/services/assistant-service/configs/default/config.yaml" "$out/configs/assistant-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/assistant-service/configs/gamma/config.yaml" "$out/configs/assistant-service/gamma/config.yaml"
  cp "$ROOT/deploy/shared/reliable_task_module_catalog.yaml" "$out/deploy/shared/reliable_task_module_catalog.yaml"
  cp "$ROOT/deploy/shared/reliable_task_retention_policy.yaml" "$out/deploy/shared/reliable_task_retention_policy.yaml"
  cp "$ROOT/quwoquan_service/services/product-ops-service/configs/default/config.yaml" "$out/configs/product-ops-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/product-ops-service/configs/gamma/config.yaml" "$out/configs/product-ops-service/gamma/config.yaml"
  cp "$ROOT/quwoquan_service/services/rec-model-service/configs/default/config.yaml" "$out/configs/recommendation-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/rec-model-service/configs/gamma/config.yaml" "$out/configs/recommendation-service/gamma/config.yaml"
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
  general:
    mode: standalone
    addr: "redis:6379"
    db: 1
rec_model_service:
  enabled: true
  url: "http://rec-model-service:8000"
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
  general:
    mode: standalone
    addr: "redis:6379"
  reliable_task:
    mode: standalone
    addr: "redis:6379"
runtime:
  media:
    group_avatar_cdn_base_url: "${MEDIA_BASE_URL}"
    group_avatar_local_media_root: "/var/lib/quwoquan/chat-media"
  sync:
    patch_ttl_hours: 720
  reliable_task:
    ready_index:
      enabled: true
      stream: "reliabletask:chat:avatar:ready:local-gamma"
      group: "chat.group_avatar_worker.local-gamma"
      queue: "reliabletask.chat.avatar"
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
  general:
    mode: standalone
    addr: "redis:6379"
    db: 1
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
  general:
    mode: standalone
    addr: "redis:6379"
    db: 1
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
}

prepare_media_root() {
  local media="$ROOT/artifacts/local-gamma/media"
  mkdir -p "$media/media/avatar" "$media/media/image" "$media/media/video"
  printf 'local-gamma avatar fixture\n' > "$media/media/avatar/local-gamma-avatar.txt"
  printf 'local-gamma image fixture\n' > "$media/media/image/local-gamma-cover.txt"
  printf 'local-gamma video fixture\n' > "$media/media/video/local-gamma-sample.txt"
}

print_defines() {
  if ! python3 - <<'PY' >/dev/null 2>&1; then
import sys
raise SystemExit(0 if sys.version_info >= (3, 7) else 1)
PY
    echo "[local-gamma] skip dart defines: python3 >= 3.7 required" >&2
    return 0
  fi

  python3 "$ROOT/scripts/print_app_env_dart_defines.py" \
    --env gamma \
    --gateway-base-url "$GATEWAY_BASE_URL" \
    --media-base-url "$MEDIA_BASE_URL"
}

if [[ "$down" == "1" ]]; then
  stop_colima_tunnels
  docker compose -f "$COMPOSE_FILE" down
  exit 0
fi

prepare_config_root
prepare_media_root

if [[ "$print_env" == "1" ]]; then
  print_defines
fi

if [[ "$skip_up" == "1" ]]; then
  echo "[local-gamma] prepared artifacts only"
  echo "[local-gamma] configVersion=$CONFIG_VERSION imageVersion=$IMAGE_VERSION"
  exit 0
fi

podman_compose=0
if docker --version 2>/dev/null | grep -qi 'podman' && command -v podman-compose >/dev/null 2>&1; then
  podman_compose=1
  compose_cmd=(podman-compose -f "$COMPOSE_FILE" --podman-build-args=--pull=never --podman-run-args=--pull=never)
  compose_up_args=(up -d --no-build)
else
  compose_cmd=(docker compose -f "$COMPOSE_FILE")
  compose_up_args=(up -d --remove-orphans)
fi

if [[ "$skip_build" == "0" ]]; then
  if ! "${compose_cmd[@]}" build; then
    if [[ "${LOCAL_GAMMA_ALLOW_CACHED_IMAGES_ON_BUILD_FAILURE:-1}" == "1" ]] && \
      docker image inspect \
        quwoquan_service-rec-model-service \
        quwoquan_service-content-service \
        quwoquan_service-chat-service >/dev/null 2>&1; then
      echo "[local-gamma] WARN: docker build failed; using existing local service images (set LOCAL_GAMMA_ALLOW_CACHED_IMAGES_ON_BUILD_FAILURE=0 to make this fatal)" >&2
    else
      exit 1
    fi
  fi
fi
export LOCAL_GAMMA_CONFIG_VERSION="$CONFIG_VERSION"
export LOCAL_GAMMA_IMAGE_VERSION="$IMAGE_VERSION"
if [[ "$podman_compose" == "1" ]]; then
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
    quwoquan_service_mongo-init_1 \
    quwoquan_service_rec-model-service_1 \
    quwoquan_service_redis_1 \
    quwoquan_service_mongodb_1 \
    quwoquan_service_postgres_1; do
    podman rm -f "$container_name" >/dev/null 2>&1 || true
  done
  podman network exists "$network_name" || podman network create "$network_name" >/dev/null
  # user-service migrations are not idempotent yet; keep gamma startup
  # deterministic by recreating the Postgres volume on each boot.
  podman volume rm -f quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || true
  podman volume inspect quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-postgres >/dev/null
  podman volume inspect quwoquan_service_local-gamma-mongo >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-mongo >/dev/null
  podman volume inspect quwoquan_service_local-gamma-redis >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-redis >/dev/null
  podman volume inspect quwoquan_service_local-gamma-go-cache >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-go-cache >/dev/null
  podman volume inspect quwoquan_service_local-gamma-caddy-data >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-caddy-data >/dev/null
  podman volume inspect quwoquan_service_local-gamma-caddy-config >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-caddy-config >/dev/null

  podman run --pull=never --name quwoquan_service_postgres_1 -d \
    --net "$network_name" --network-alias postgres \
    -e POSTGRES_USER=quwoquan -e POSTGRES_PASSWORD=quwoquan -e POSTGRES_DB=quwoquan \
    -v quwoquan_service_local-gamma-postgres:/var/lib/postgresql/data \
    -p "${LOCAL_GAMMA_POSTGRES_PORT:-55432}:5432" \
    --healthcheck-command "pg_isready -U quwoquan" \
    --healthcheck-interval 5s --healthcheck-timeout 3s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_POSTGRES_IMAGE" >/dev/null

  podman run --pull=never --name quwoquan_service_mongodb_1 -d \
    --net "$network_name" --network-alias mongodb \
    -v quwoquan_service_local-gamma-mongo:/data/db \
    -p "${LOCAL_GAMMA_MONGO_PORT:-37017}:27017" \
    "$LOCAL_GAMMA_MONGO_IMAGE" --replSet rs0 --bind_ip_all >/dev/null

  podman run --pull=never --name quwoquan_service_redis_1 -d \
    --net "$network_name" --network-alias redis \
    -v quwoquan_service_local-gamma-redis:/data \
    -p "${LOCAL_GAMMA_REDIS_PORT:-36379}:6379" \
    --healthcheck-command "redis-cli ping" \
    --healthcheck-interval 5s --healthcheck-timeout 3s --healthcheck-retries 20 \
    "$LOCAL_GAMMA_REDIS_IMAGE" redis-server --appendonly yes >/dev/null

  wait_healthy quwoquan_service_postgres_1
  wait_running quwoquan_service_mongodb_1
  sleep 5
  wait_healthy quwoquan_service_redis_1

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
    --net "$network_name" --network-alias rec-model-service \
    -e SERVICE_NAME=recommendation-service -e APP_ENV=gamma \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PYTHONUNBUFFERED=1 \
    -v "$ROOT/artifacts/local-gamma/config-root:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_REC_MODEL_PORT:-18090}:8000" \
    --healthcheck-command "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\" || exit 1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 5 \
    quwoquan_service_rec-model-service >/dev/null
  wait_healthy quwoquan_service_rec-model-service_1

  podman run --pull=never --name quwoquan_service_product-ops-service_1 -d \
    --net "$network_name" --network-alias product-ops-service \
    -e PATH=/go/bin:/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    -e GOPROXY="${LOCAL_GAMMA_GOPROXY:-https://goproxy.cn,direct}" \
    -e GOSUMDB="${LOCAL_GAMMA_GOSUMDB:-sum.golang.google.cn}" \
    -e SERVICE_NAME=product-ops-service -e APP_ENV=gamma \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PRODUCT_OPS_SERVICE_ADDR=:18086 \
    -e MONGO_URI=mongodb://mongodb:27017 \
    -e PRODUCT_OPS_REDIS_REC_ADDR=redis:6379 -e PRODUCT_OPS_REDIS_GENERAL_ADDR=redis:6379 \
    -v "$ROOT/quwoquan_service:/workspace" \
    -v "$ROOT/artifacts/local-gamma/config-root:/etc/qwq-config:ro" \
    -v quwoquan_service_local-gamma-go-cache:/go \
    -p "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-18086}:18086" \
    -w /workspace \
    --healthcheck-command "wget -qO- http://127.0.0.1:18086/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_GO_BOOKWORM_IMAGE" sh -lc "cd services/product-ops-service/cmd/api && /usr/local/go/bin/go run ." >/dev/null
  wait_healthy quwoquan_service_product-ops-service_1

  podman run --pull=never --name quwoquan_service_content-service_1 -d \
    --net "$network_name" --network-alias content-service \
    -e SERVICE_NAME=content-service -e APP_ENV=gamma \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e MONGO_URI=mongodb://mongodb:27017 \
    -e CONTENT_REDIS_REC_ADDR=redis:6379 -e CONTENT_REDIS_GENERAL_ADDR=redis:6379 \
    -e REC_MODEL_SERVICE_ENABLED=true -e REC_MODEL_SERVICE_URL=http://rec-model-service:8000 \
    -v "$ROOT/artifacts/local-gamma/config-root:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_CONTENT_PORT:-18083}:18080" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18080/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    quwoquan_service_content-service >/dev/null
  wait_healthy quwoquan_service_content-service_1

  podman run --pull=never --name quwoquan_service_chat-service_1 -d \
    --net "$network_name" --network-alias chat-service \
    -e SERVICE_NAME=chat-service -e MODULE_PACKAGE=chat-service -e APP_ENV=gamma \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e CHAT_SERVICE_ADDR=:18081 \
    -e MONGO_URI=mongodb://mongodb:27017 -e MONGO_DATABASE=quwoquan_chat \
    -e CHAT_REDIS_REALTIME_ADDR=redis:6379 -e CHAT_REDIS_GENERAL_ADDR=redis:6379 \
    -e CHAT_REDIS_RELIABLE_TASK_ADDR=redis:6379 \
    -e RELIABLE_TASK_READY_INDEX_ENABLED=true \
    -e RELIABLE_TASK_READY_INDEX_STREAM=reliabletask:chat:avatar:ready:local-gamma \
    -e RELIABLE_TASK_READY_INDEX_GROUP=chat.group_avatar_worker.local-gamma \
    -e RELIABLE_TASK_READY_INDEX_QUEUE=reliabletask.chat.avatar \
    -e CHAT_GROUP_AVATAR_CDN_BASE_URL="$MEDIA_BASE_URL" \
    -e CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT=/var/lib/quwoquan/chat-media \
    -e RUNTIME_SYNC_PATCH_TTL_HOURS=720 \
    -v "$ROOT/artifacts/local-gamma/config-root:/etc/qwq-config:ro" \
    -v "$ROOT/artifacts/local-gamma/media:/var/lib/quwoquan/chat-media" \
    -p "${LOCAL_GAMMA_CHAT_PORT:-18081}:18081" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18081/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    quwoquan_service_chat-service >/dev/null
  wait_healthy quwoquan_service_chat-service_1

  podman run --pull=never --name quwoquan_service_user-service_1 -d \
    --net "$network_name" --network-alias user-service \
    -e PATH=/go/bin:/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    -e GOPROXY="${LOCAL_GAMMA_GOPROXY:-https://goproxy.cn,direct}" \
    -e GOSUMDB="${LOCAL_GAMMA_GOSUMDB:-sum.golang.google.cn}" \
    -e SERVICE_NAME=user-service -e APP_ENV=gamma \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e USER_SERVICE_ADDR=:18082 \
    -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_user \
    -e REDIS_ADDR=redis:6379 \
    -v "$ROOT/quwoquan_service:/workspace" \
    -v "$ROOT/artifacts/local-gamma/config-root:/etc/qwq-config:ro" \
    -v quwoquan_service_local-gamma-go-cache:/go \
    -w /workspace/services/user-service \
    -p "${LOCAL_GAMMA_USER_PORT:-18082}:18082" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18082/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_GO_BOOKWORM_IMAGE" sh -lc "/usr/local/go/bin/go run ./cmd/api" >/dev/null
  wait_healthy quwoquan_service_user-service_1

  podman run --pull=never --name quwoquan_service_assistant-service_1 -d \
    --net "$network_name" --network-alias assistant-service \
    -e PATH=/go/bin:/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    -e GOPROXY="${LOCAL_GAMMA_GOPROXY:-https://goproxy.cn,direct}" \
    -e GOSUMDB="${LOCAL_GAMMA_GOSUMDB:-sum.golang.google.cn}" \
    -e SERVICE_NAME=assistant-service -e APP_ENV=gamma \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e ASSISTANT_SERVICE_ADDR=:18087 \
    -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_assistant \
    -e REDIS_GENERAL_ADDR=redis:6379 -e REDIS_REC_ADDR=redis:6379 \
    -e ASSISTANT_MODEL_PROVIDER="${ASSISTANT_MODEL_PROVIDER:-deterministic}" \
    -e ALLOW_DETERMINISTIC_BETA="${ALLOW_DETERMINISTIC_BETA:-1}" \
    -e ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-assistant_p0_core}" \
    -e ASSISTANT_SEARCH_PROVIDER="${ASSISTANT_SEARCH_PROVIDER:-}" \
    -v "$ROOT/quwoquan_service:/workspace" \
    -v "$ROOT/artifacts/local-gamma/config-root:/etc/qwq-config:ro" \
    -v quwoquan_service_local-gamma-go-cache:/go \
    -w /workspace \
    --healthcheck-command "wget -qO- http://127.0.0.1:18087/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_GO_BOOKWORM_IMAGE" sh -lc "cd services/assistant-service/cmd/api && /usr/local/go/bin/go run ." >/dev/null
  wait_healthy quwoquan_service_assistant-service_1

  podman run --pull=never --name quwoquan_service_gamma-proxy_1 -d \
    --net "$network_name" --network-alias gamma-proxy \
    -e LOCAL_GAMMA_TLS_MODE="${LOCAL_GAMMA_TLS_MODE:-internal}" \
    -v "$ROOT/deploy/local-gamma/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$ROOT/artifacts/local-gamma/media:/srv/media:ro" \
    -v quwoquan_service_local-gamma-caddy-data:/data \
    -v quwoquan_service_local-gamma-caddy-config:/config \
    -p "${LOCAL_GAMMA_HTTP_PORT:-18080}:80" \
    -p "${LOCAL_GAMMA_HTTPS_PORT:-443}:443" \
    -p "${LOCAL_GAMMA_ADMIN_PORT:-2019}:2019" \
    --healthcheck-command "wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 5s --healthcheck-retries 10 \
    docker.io/library/caddy:2.8-alpine >/dev/null
  wait_healthy quwoquan_service_gamma-proxy_1
else
  # Recreate the local mirror on every gate run so changed host port envs take effect.
  "${compose_cmd[@]}" down --remove-orphans >/dev/null 2>&1 || true
  docker volume rm -f quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || true
  "${compose_cmd[@]}" "${compose_up_args[@]}"
fi
start_colima_tunnels_if_needed

# docker compose 分支不会逐项 wait_healthy；在宣告就绪前用主机侧探测避免 T3/T4 撞到端口未监听。
wait_local_gamma_host_ready() {
  local gw="${GATEWAY_BASE_URL%/}"
  local gw_local="http://127.0.0.1:${LOCAL_GAMMA_HTTP_PORT:-18080}"
  local po_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-18086}"
  local user_port="${LOCAL_GAMMA_USER_PORT:-18082}"
  local deadline=$(( $(date +%s) + 180 ))
  echo "[local-gamma] waiting for host probes: ${gw}/healthz or ${gw_local}/healthz + http://127.0.0.1:${po_port}/healthz + http://127.0.0.1:${user_port}/healthz"
  while (( $(date +%s) < deadline )); do
    if python3 - <<PY
import urllib.request
gateway_urls = ["${gw}/healthz"]
if "${gw_local}/healthz" not in gateway_urls:
    gateway_urls.append("${gw_local}/healthz")
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
  echo "[local-gamma] FAIL: host cannot reach ${gw}/healthz or ${gw_local}/healthz plus http://127.0.0.1:${po_port}/healthz within 180s" >&2
  return 1
}
wait_local_gamma_host_ready

echo "[local-gamma] mirror started"
echo "[local-gamma] gateway: $GATEWAY_BASE_URL"
echo "[local-gamma] product-ops: $PRODUCT_OPS_BASE_URL"
echo "[local-gamma] media: $MEDIA_BASE_URL"
echo "[local-gamma] dart defines:"
print_defines
