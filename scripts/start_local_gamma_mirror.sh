#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/quwoquan_service/docker-compose.gamma-local.yaml"
CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-local-gamma-v1}"
IMAGE_VERSION="${LOCAL_GAMMA_IMAGE_VERSION:-0.0.1}"
GATEWAY_BASE_URL="${LOCAL_GAMMA_GATEWAY_BASE_URL:-https://gamma-api.quwoquan-env.test}"
PRODUCT_OPS_BASE_URL="${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-https://gamma-product-ops.quwoquan-env.test}"
MEDIA_BASE_URL="${LOCAL_GAMMA_MEDIA_BASE_URL:-https://gamma-image.quwoquan-env.test}"

skip_build=0
skip_up=0
print_env=0
down=0

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
    "$out/configs/product-ops-service/default" \
    "$out/configs/product-ops-service/gamma" \
    "$out/releases/config/product-ops-service" \
    "$out/configs/recommendation-service/default" \
    "$out/configs/recommendation-service/gamma" \
    "$out/releases/config/recommendation-service"
  cp "$ROOT/quwoquan_service/services/content-service/configs/default/config.yaml" "$out/configs/content-service/default/config.yaml"
  cp "$ROOT/quwoquan_service/services/content-service/configs/gamma/config.yaml" "$out/configs/content-service/gamma/config.yaml"
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
  compose_up_args=(up -d)
fi

if [[ "$skip_build" == "0" ]]; then
  "${compose_cmd[@]}" build
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
  podman rm -f \
    quwoquan_service_gamma-proxy_1 \
    quwoquan_service_content-service_1 \
    quwoquan_service_product-ops-service_1 \
    quwoquan_service_mongo-init_1 \
    quwoquan_service_rec-model-service_1 \
    quwoquan_service_redis_1 \
    quwoquan_service_mongodb_1 \
    quwoquan_service_postgres_1 >/dev/null 2>&1 || true
  podman network exists "$network_name" || podman network create "$network_name" >/dev/null
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
    docker.io/library/postgres:16-alpine >/dev/null

  podman run --pull=never --name quwoquan_service_mongodb_1 -d \
    --net "$network_name" --network-alias mongodb \
    -v quwoquan_service_local-gamma-mongo:/data/db \
    -p "${LOCAL_GAMMA_MONGO_PORT:-37017}:27017" \
    docker.io/library/mongo:7-jammy --replSet rs0 --bind_ip_all >/dev/null

  podman run --pull=never --name quwoquan_service_redis_1 -d \
    --net "$network_name" --network-alias redis \
    -v quwoquan_service_local-gamma-redis:/data \
    -p "${LOCAL_GAMMA_REDIS_PORT:-36379}:6379" \
    --healthcheck-command "redis-cli ping" \
    --healthcheck-interval 5s --healthcheck-timeout 3s --healthcheck-retries 20 \
    docker.io/library/redis:7.2-alpine redis-server --appendonly yes >/dev/null

  wait_healthy quwoquan_service_postgres_1
  wait_running quwoquan_service_mongodb_1
  sleep 5
  wait_healthy quwoquan_service_redis_1

  podman run --pull=never --rm --name quwoquan_service_mongo-init_1 \
    --net "$network_name" --network-alias mongo-init \
    docker.io/library/mongo:7-jammy bash -lc "mongosh --host mongodb:27017 --quiet --eval '
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
    docker.io/library/golang:1.24-bookworm sh -lc "cd services/product-ops-service/cmd/api && /usr/local/go/bin/go run ." >/dev/null
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
    -p "${LOCAL_GAMMA_CONTENT_PORT:-18080}:18080" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18080/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    quwoquan_service_content-service >/dev/null
  wait_healthy quwoquan_service_content-service_1

  podman run --pull=never --name quwoquan_service_gamma-proxy_1 -d \
    --net "$network_name" --network-alias gamma-proxy \
    -e LOCAL_GAMMA_TLS_MODE="${LOCAL_GAMMA_TLS_MODE:-internal}" \
    -v "$ROOT/deploy/local-gamma/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$ROOT/artifacts/local-gamma/media:/srv/media:ro" \
    -v quwoquan_service_local-gamma-caddy-data:/data \
    -v quwoquan_service_local-gamma-caddy-config:/config \
    -p "${LOCAL_GAMMA_HTTP_PORT:-80}:80" \
    -p "${LOCAL_GAMMA_HTTPS_PORT:-443}:443" \
    -p "${LOCAL_GAMMA_ADMIN_PORT:-2019}:2019" \
    --healthcheck-command "wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 5s --healthcheck-retries 10 \
    docker.io/library/caddy:2.8-alpine >/dev/null
  wait_healthy quwoquan_service_gamma-proxy_1
else
  "${compose_cmd[@]}" "${compose_up_args[@]}"
fi

echo "[local-gamma] mirror started"
echo "[local-gamma] gateway: $GATEWAY_BASE_URL"
echo "[local-gamma] product-ops: $PRODUCT_OPS_BASE_URL"
echo "[local-gamma] media: $MEDIA_BASE_URL"
echo "[local-gamma] dart defines:"
print_defines
