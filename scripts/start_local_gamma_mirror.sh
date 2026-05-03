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

  "${compose_cmd[@]}" down || true
  "${compose_cmd[@]}" up -d --no-build --no-deps postgres mongodb redis
  wait_healthy quwoquan_service_postgres_1
  wait_healthy quwoquan_service_mongodb_1
  wait_healthy quwoquan_service_redis_1
  "${compose_cmd[@]}" up -d --no-build --no-deps mongo-init
  wait_exited_zero quwoquan_service_mongo-init_1
  "${compose_cmd[@]}" up -d --no-build --no-deps rec-model-service
  wait_healthy quwoquan_service_rec-model-service_1
  "${compose_cmd[@]}" up -d --no-build --no-deps product-ops-service
  wait_healthy quwoquan_service_product-ops-service_1
  "${compose_cmd[@]}" up -d --no-build --no-deps content-service
  wait_healthy quwoquan_service_content-service_1
  "${compose_cmd[@]}" up -d --no-build --no-deps gamma-proxy
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
