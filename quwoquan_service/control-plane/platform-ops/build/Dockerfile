ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG GO_BUILD_FLAGS=-p=1

FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG TARGETOS
ARG TARGETARCH
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /build/quwoquan_service
COPY quwoquan_service/go.mod quwoquan_service/go.sum ./
RUN go mod download
COPY quwoquan_service/ ./
COPY quwoquan_ops/environments/ /build/quwoquan_ops/environments/
COPY quwoquan_ops/external/ /build/quwoquan_ops/external/
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /platform-ops-service ./control-plane/platform-ops/cmd/api
RUN set -eux; \
    facts=/runtime-facts; \
    mkdir -p "$facts/quwoquan_service/services" \
      "$facts/quwoquan_service/control-plane/platform-ops" \
      "$facts/quwoquan_ops"; \
    for service_root in services/*; do \
      service_id="$(basename "$service_root")"; \
      target="$facts/quwoquan_service/services/$service_id"; \
      mkdir -p "$target"; \
      cp -R "$service_root/config" "$service_root/environments" "$target/"; \
    done; \
    cp -R control-plane/platform-ops/config control-plane/platform-ops/deploy \
      control-plane/platform-ops/environments \
      "$facts/quwoquan_service/control-plane/platform-ops/"; \
    cp -R /build/quwoquan_ops/environments /build/quwoquan_ops/external \
      "$facts/quwoquan_ops/"

FROM ${ALPINE_BASE_IMAGE}
RUN if command -v apk >/dev/null 2>&1; then \
      apk add --no-cache ca-certificates tzdata; \
    else \
      apt-get update \
      && apt-get install -y --no-install-recommends ca-certificates tzdata \
      && rm -rf /var/lib/apt/lists/*; \
    fi
WORKDIR /app
COPY --from=builder /platform-ops-service /usr/local/bin/platform-ops-service
COPY --from=builder /runtime-facts/ /app/
ENV REPO_ROOT=/app
EXPOSE 18088
CMD ["platform-ops-service"]
