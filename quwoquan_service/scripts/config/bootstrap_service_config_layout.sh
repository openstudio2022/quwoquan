#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  quwoquan_service/scripts/config/bootstrap_service_config_layout.sh \
    --service-name <name> --service-port <port>

Creates the canonical default/alpha/beta/gamma/prod service config files.
Existing files are never overwritten.
EOF
}

SERVICE_NAME=""
SERVICE_PORT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service-name)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --service-port)
      SERVICE_PORT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$SERVICE_NAME" =~ ^[a-z0-9]+([a-z0-9-]*[a-z0-9])?-service$ ]]; then
  echo "FAIL: invalid --service-name: $SERVICE_NAME" >&2
  exit 2
fi

if [[ ! "$SERVICE_PORT" =~ ^[0-9]+$ ]] || (( SERVICE_PORT < 1 || SERVICE_PORT > 65535 )); then
  echo "FAIL: --service-port must be between 1 and 65535" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="$SERVICE_ROOT/services/$SERVICE_NAME/configs"
if [[ ! -d "$SERVICE_ROOT/services/$SERVICE_NAME" ]]; then
  echo "FAIL: service directory does not exist: $SERVICE_ROOT/services/$SERVICE_NAME" >&2
  exit 2
fi

for env_name in default alpha beta gamma prod; do
  env_dir="$TARGET/$env_name"
  config_file="$env_dir/config.yaml"
  mkdir -p "$env_dir"
  if [[ -e "$config_file" ]]; then
    echo "FAIL: refusing to overwrite $config_file" >&2
    exit 1
  fi
  cat >"$config_file" <<EOF
config:
  version: v0
  min_image_version: 0.0.0
  max_image_version: 999.999.999
service:
  name: ${SERVICE_NAME}
  environment: ${env_name}
  http:
    addr: ":${SERVICE_PORT}"
EOF
done

echo "[scaffold] service config layout created: $TARGET"
