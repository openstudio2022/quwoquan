ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG GO_BUILD_FLAGS=-p=1
ARG QWQ_ARTIFACT_ENVIRONMENT
ARG QWQ_ARTIFACT_CONFIG_DIGEST

FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG QWQ_ARTIFACT_ENVIRONMENT
ARG QWQ_ARTIFACT_CONFIG_DIGEST
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
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /platform-ops-service ./control-plane/platform-ops/cmd/api
RUN set -eux; \
    case "${QWQ_ARTIFACT_ENVIRONMENT}" in alpha|beta|gamma|prod) ;; *) exit 2 ;; esac; \
    facts=/runtime-facts; \
    mkdir -p "$facts/quwoquan_service/services" \
      "$facts/quwoquan_service/control-plane/platform-ops/environments" \
      "$facts/quwoquan_ops/environments"; \
    for service_root in services/*; do \
      service_id="$(basename "$service_root")"; \
      environment_root="$service_root/environments/${QWQ_ARTIFACT_ENVIRONMENT}"; \
      test -d "$environment_root" || continue; \
      target="$facts/quwoquan_service/services/$service_id"; \
      mkdir -p "$target/environments"; \
      cp -R "$service_root/config" "$target/"; \
      cp -R "$environment_root" "$target/environments/${QWQ_ARTIFACT_ENVIRONMENT}"; \
    done; \
    cp -R control-plane/platform-ops/config \
      "$facts/quwoquan_service/control-plane/platform-ops/"; \
    cp -R "control-plane/platform-ops/environments/${QWQ_ARTIFACT_ENVIRONMENT}" \
      "$facts/quwoquan_service/control-plane/platform-ops/environments/${QWQ_ARTIFACT_ENVIRONMENT}"; \
    cp -R "/build/quwoquan_ops/environments/${QWQ_ARTIFACT_ENVIRONMENT}" \
      "$facts/quwoquan_ops/environments/${QWQ_ARTIFACT_ENVIRONMENT}"

FROM ${ALPINE_BASE_IMAGE}
ARG QWQ_ARTIFACT_ENVIRONMENT
ARG QWQ_ARTIFACT_CONFIG_DIGEST
RUN set -eu; \
    case "${QWQ_ARTIFACT_ENVIRONMENT}" in alpha|beta|gamma|prod) ;; *) exit 2 ;; esac; \
    digest_hex="${QWQ_ARTIFACT_CONFIG_DIGEST#sha256:}"; \
    test "${#digest_hex}" -eq 64; \
    test -z "$(printf '%s' "${digest_hex}" | tr -d '0-9a-f')"; \
    install -d /etc/quwoquan; \
    printf '{"schema":"qwq.environment-artifact-identity","environment":"%s","configDigest":"%s"}\n' \
      "${QWQ_ARTIFACT_ENVIRONMENT}" "${QWQ_ARTIFACT_CONFIG_DIGEST}" \
      > /etc/quwoquan/artifact-identity.json; \
    chmod 0444 /etc/quwoquan/artifact-identity.json
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
