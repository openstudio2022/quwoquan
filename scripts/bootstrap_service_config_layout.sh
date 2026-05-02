#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  scripts/bootstrap_service_config_layout.sh --service <service-name> [--force]

Examples:
  scripts/bootstrap_service_config_layout.sh --service content-service
  scripts/bootstrap_service_config_layout.sh --service user-service --force

Behavior:
  - Creates per-service env-split config layout:
      quwoquan_service/services/<service>/configs/default/config.yaml
      quwoquan_service/services/<service>/configs/alpha/config.yaml
      quwoquan_service/services/<service>/configs/beta/config.yaml
      quwoquan_service/services/<service>/configs/gamma/config.yaml
      quwoquan_service/services/<service>/configs/prod-gray/config.yaml
      quwoquan_service/services/<service>/configs/prod/config.yaml
  - Creates versioned config release directory:
      releases/config/<service>/
  - Does NOT overwrite existing files unless --force is passed.
EOF
}

SERVICE_NAME=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$SERVICE_NAME" ]]; then
  echo "FAIL: --service is required" >&2
  usage
  exit 2
fi

svc_root="$ROOT/quwoquan_service/services/$SERVICE_NAME"
if [[ ! -d "$svc_root" ]]; then
  echo "FAIL: service directory not found: $svc_root" >&2
  echo "Hint: create service skeleton first, then bootstrap config layout." >&2
  exit 1
fi

configs_root="$svc_root/configs"
default_cfg="$configs_root/default/config.yaml"
alpha_cfg="$configs_root/alpha/config.yaml"
beta_cfg="$configs_root/beta/config.yaml"
gamma_cfg="$configs_root/gamma/config.yaml"
prod_gray_cfg="$configs_root/prod-gray/config.yaml"
prod_cfg="$configs_root/prod/config.yaml"
current_cfg="$configs_root/config.yaml"

mkdir -p "$(dirname "$default_cfg")" "$(dirname "$alpha_cfg")" "$(dirname "$beta_cfg")" "$(dirname "$gamma_cfg")" "$(dirname "$prod_gray_cfg")" "$(dirname "$prod_cfg")"

write_file() {
  local path="$1"
  local content="$2"
  if [[ -f "$path" && "$FORCE" -ne 1 ]]; then
    echo "SKIP: exists $path"
    return
  fi
  printf "%s" "$content" > "$path"
  echo "OK: wrote $path"
}

DEFAULT_CONTENT="$(cat <<EOF
service:
  name: $SERVICE_NAME
  http:
    addr: ":18080"

config:
  # Config release contract
  # CONFIG_VERSION must be injected by deployment pipeline in prod.
  version: "v0.0.1"
  min_image_version: "0.0.1"
  max_image_version: "9.9.9"

# Redis scenes (defaults)
redis:
  rec:
    mode: standalone
    addr: ""
    addrs: []
    password: ""
    db: 0
    tls: false
    pool:
      size: 0
      min_idle: 0
      read_timeout_ms: 100
      write_timeout_ms: 100
      dial_timeout_ms: 500
  general:
    mode: standalone
    addr: ""
    addrs: []
    password: ""
    db: 1
    tls: false
    pool:
      size: 0
      min_idle: 0
      read_timeout_ms: 200
      write_timeout_ms: 200
      dial_timeout_ms: 500
EOF
)"

ALPHA_CONTENT="$(cat <<'EOF'
# alpha overrides (developer single-instance validation)
service:
  http:
    addr: ":18080"

redis:
  rec:
    mode: standalone
    addr: "127.0.0.1:6379"
    db: 0
EOF
)"

BETA_CONTENT="$(cat <<'EOF'
# beta overrides (developer local cloud-client integration)
service:
  http:
    addr: ":18080"

redis:
  rec:
    mode: standalone
    addr: "127.0.0.1:6379"
    db: 0
EOF
)"

GAMMA_CONTENT="$(cat <<'EOF'
# gamma overrides (cloud integration env)
service:
  http:
    addr: ":18080"

redis:
  rec:
    mode: standalone
    addr: ""
    db: 0
EOF
)"

PROD_GRAY_CONTENT="$(cat <<'EOF'
# prod-gray overrides (production gray release)
# Recommend injecting APP_ENV=prod-gray, CONFIG_VERSION, IMAGE_VERSION, CONFIG_ROOT via env.
service:
  http:
    addr: ":18080"

redis:
  rec:
    mode: cluster
    addrs: []
    tls: true
EOF
)"

PROD_CONTENT="$(cat <<'EOF'
# prod overrides (container/k8s)
# Recommend injecting APP_ENV=prod, CONFIG_VERSION, IMAGE_VERSION, CONFIG_ROOT via env.
service:
  http:
    addr: ":18080"

redis:
  rec:
    mode: cluster
    addrs: []
    tls: true
EOF
)"

write_file "$default_cfg" "$DEFAULT_CONTENT"
write_file "$alpha_cfg" "$ALPHA_CONTENT"
write_file "$beta_cfg" "$BETA_CONTENT"
write_file "$gamma_cfg" "$GAMMA_CONTENT"
write_file "$prod_gray_cfg" "$PROD_GRAY_CONTENT"
write_file "$prod_cfg" "$PROD_CONTENT"

release_dir="$ROOT/releases/config/$SERVICE_NAME"
mkdir -p "$release_dir"
if [[ ! -f "$release_dir/README.md" || "$FORCE" -eq 1 ]]; then
  cat > "$release_dir/README.md" <<'EOF'
# Versioned Config Releases

Put immutable config release snapshots here:

- vYYYY.MM.DD.N.yaml

Example:
- v2026.02.27.1.yaml

Do not overwrite existing versions; always create a new version file.
EOF
  echo "OK: wrote $release_dir/README.md"
fi

if [[ -f "$current_cfg" ]]; then
  echo "WARN: current file exists: $current_cfg"
  echo "      Consider migrating it into default/alpha/beta/gamma/prod-gray/prod split files."
fi

echo "DONE: service config layout bootstrapped for $SERVICE_NAME"
