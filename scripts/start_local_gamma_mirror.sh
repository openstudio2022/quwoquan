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

compose_args=(-f "$COMPOSE_FILE")
if [[ "$skip_build" == "0" ]]; then
  docker compose "${compose_args[@]}" build
fi
LOCAL_GAMMA_CONFIG_VERSION="$CONFIG_VERSION" \
LOCAL_GAMMA_IMAGE_VERSION="$IMAGE_VERSION" \
docker compose "${compose_args[@]}" up -d

echo "[local-gamma] mirror started"
echo "[local-gamma] gateway: $GATEWAY_BASE_URL"
echo "[local-gamma] product-ops: $PRODUCT_OPS_BASE_URL"
echo "[local-gamma] media: $MEDIA_BASE_URL"
echo "[local-gamma] dart defines:"
print_defines
