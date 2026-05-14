#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  agent_ops/scaffold/new_service_fullstack.sh --name <service-name> [--port <port>]

Examples:
  agent_ops/scaffold/new_service_fullstack.sh --name user-service --port 18081
  agent_ops/scaffold/new_service_fullstack.sh --name chat-service

Notes:
  - Service name should include '-service' suffix.
  - Script scaffolds a minimal DDD directory layout.
  - Script always bootstraps env-split config layout by calling:
      quwoquan_service/scripts/runtime/bootstrap_service_config_layout.sh --service <service-name>
EOF
}

SERVICE_NAME=""
SERVICE_PORT="18080"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --port)
      SERVICE_PORT="${2:-}"
      shift 2
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
  echo "FAIL: --name is required" >&2
  usage
  exit 2
fi

if [[ ! "$SERVICE_NAME" =~ -service$ ]]; then
  echo "FAIL: service name must end with '-service' (got: $SERVICE_NAME)" >&2
  exit 2
fi

if ! [[ "$SERVICE_PORT" =~ ^[0-9]+$ ]]; then
  echo "FAIL: --port must be numeric (got: $SERVICE_PORT)" >&2
  exit 2
fi

svc_root="$ROOT/quwoquan_service/services/$SERVICE_NAME"
if [[ -e "$svc_root" ]]; then
  echo "FAIL: service already exists: $svc_root" >&2
  exit 1
fi

mkdir -p \
  "$svc_root/cmd/api" \
  "$svc_root/internal/domain" \
  "$svc_root/internal/application" \
  "$svc_root/internal/adapters/http" \
  "$svc_root/internal/adapters/mq" \
  "$svc_root/internal/infrastructure/persistence" \
  "$svc_root/internal/infrastructure/cache" \
  "$svc_root/internal/infrastructure/migration" \
  "$svc_root/tests" \
  "$svc_root/configs"

cat >"$svc_root/cmd/api/main.go" <<EOF
package main

import "log"

func main() {
\tlog.Printf("${SERVICE_NAME} bootstrap placeholder; port=:${SERVICE_PORT}")
}
EOF

cat >"$svc_root/go.mod" <<EOF
module quwoquan_service/services/${SERVICE_NAME}

go 1.24.0
EOF

cat >"$svc_root/Makefile" <<'EOF'
.PHONY: build test

build:
	go build ./...

test:
	go test ./... -count=1
EOF

# Keep a current single-file config for backward compatibility during migration.
cat >"$svc_root/configs/config.yaml" <<EOF
service:
  name: ${SERVICE_NAME}
  http:
    addr: ":${SERVICE_PORT}"
EOF

# IMPORTANT: always bootstrap env-split config layout for new services.
bash "$ROOT/quwoquan_service/scripts/runtime/bootstrap_service_config_layout.sh" --service "$SERVICE_NAME"

echo "DONE: created new service scaffold: $svc_root"
echo "NEXT:"
echo "  1) fill cmd/api/main.go with runtime bootstrap flow"
echo "  2) fill configs/default/local/integration/prod/config.yaml"
echo "  3) create first versioned config in releases/config/${SERVICE_NAME}/v*.yaml"
