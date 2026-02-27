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
      quwoquan_service/services/<service>/configs/local/config.yaml
      quwoquan_service/services/<service>/configs/integration/config.yaml
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
local_cfg="$configs_root/local/config.yaml"
integration_cfg="$configs_root/integration/config.yaml"
prod_cfg="$configs_root/prod/config.yaml"
legacy_cfg="$configs_root/config.yaml"

mkdir -p "$(dirname "$default_cfg")" "$(dirname "$local_cfg")" "$(dirname "$integration_cfg")" "$(dirname "$prod_cfg")"

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

LOCAL_CONTENT="$(cat <<'EOF'
# local overrides (developer laptop)
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

INTEGRATION_CONTENT="$(cat <<'EOF'
# integration overrides (shared test env)
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
write_file "$local_cfg" "$LOCAL_CONTENT"
write_file "$integration_cfg" "$INTEGRATION_CONTENT"
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

if [[ -f "$legacy_cfg" ]]; then
  echo "WARN: legacy file exists: $legacy_cfg"
  echo "      Consider migrating it into default/local/integration/prod split files."
fi

echo "DONE: service config layout bootstrapped for $SERVICE_NAME"
