#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  quwoquan_ops/gate/scaffold/new_service_fullstack.sh --name <service-name> \
    --domain <domain> --profile <go-domain-source|go-control-plane-source> [--port <port>]

Examples:
  quwoquan_ops/gate/scaffold/new_service_fullstack.sh --name user-service \
    --domain user --profile go-domain-source --port 18081

Notes:
  - Service name should include '-service' suffix.
  - Script scaffolds a typed canonical DDD source layout.
  - The new asset must be registered in quwoquan_service/service_asset_profiles.json.
  - Script always bootstraps env-split config layout by calling:
      quwoquan_service/scripts/runtime/bootstrap_service_config_layout.sh --service <service-name>
EOF
}

SERVICE_NAME=""
SERVICE_PORT="18080"
SERVICE_DOMAIN=""
ASSET_PROFILE=""

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
    --domain)
      SERVICE_DOMAIN="${2:-}"
      shift 2
      ;;
    --profile)
      ASSET_PROFILE="${2:-}"
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

if [[ -z "$SERVICE_DOMAIN" ]]; then
  echo "FAIL: --domain is required" >&2
  exit 2
fi

if [[ "$ASSET_PROFILE" != "go-domain-source" && "$ASSET_PROFILE" != "go-control-plane-source" ]]; then
  echo "FAIL: --profile must be go-domain-source or go-control-plane-source" >&2
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
  "$svc_root/tests/local_contract" \
  "$svc_root/tests/api_integration" \
  "$svc_root/tests/adapter_conformance" \
  "$svc_root/tests/support" \
  "$svc_root/configs" \
  "$svc_root/deploy"

cat >"$svc_root/cmd/api/main.go" <<EOF
package main

import (
\t"log"
\t"net/http"
\t"time"

\trthttp "quwoquan_service/runtime/http"
)

func main() {
\tmux := http.NewServeMux()
\tmux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
\t\tw.WriteHeader(http.StatusOK)
\t})
\tserver := &http.Server{
\t\tAddr:              ":${SERVICE_PORT}",
\t\tHandler:           mux,
\t\tReadHeaderTimeout: 5 * time.Second,
\t}
\tif err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
\t\tlog.Fatalf("${SERVICE_NAME}: %v", err)
\t}
}
EOF

cat >"$svc_root/Makefile" <<EOF
.PHONY: build test

build:
\t@mkdir -p ../../../.qwq_output/build/${SERVICE_NAME}
\t@cd ../.. && go build -o ../.qwq_output/build/${SERVICE_NAME}/api ./services/${SERVICE_NAME}/cmd/api

test:
\t@cd ../.. && go test ./services/${SERVICE_NAME}/... -count=1
EOF

cat >"$svc_root/README.md" <<EOF
# ${SERVICE_NAME}

- Asset profile: \`${ASSET_PROFILE}\`
- ContractGraph domain: \`${SERVICE_DOMAIN}\`
- Build output: \`.qwq_output/build/${SERVICE_NAME}/api\`

The service remains non-deployable until metadata ownership, production wiring,
tests, observability, rollback evidence, and \`service_asset_profiles.json\`
registration are complete.
EOF

cat >"$svc_root/deploy/Dockerfile" <<EOF
ARG GO_BASE_IMAGE=golang:1.24-bookworm
FROM \${GO_BASE_IMAGE} AS builder
WORKDIR /build/quwoquan_service
COPY quwoquan_service/go.mod quwoquan_service/go.sum ./
RUN go mod download
COPY quwoquan_service/ ./
RUN CGO_ENABLED=0 go build -o /out/api ./services/${SERVICE_NAME}/cmd/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/api /app/api
USER nonroot:nonroot
ENTRYPOINT ["/app/api"]
EOF

# IMPORTANT: always bootstrap env-split config layout for new services.
bash "$ROOT/quwoquan_service/scripts/runtime/bootstrap_service_config_layout.sh" --service "$SERVICE_NAME"

echo "DONE: created new service scaffold: $svc_root"
echo "NEXT:"
echo "  1) fill cmd/api/main.go with runtime bootstrap flow"
echo "  2) fill configs/default/alpha/beta/gamma/prod/config.yaml"
echo "  3) create first versioned config in quwoquan_service/services/${SERVICE_NAME}/configs/releases/v*.yaml"
