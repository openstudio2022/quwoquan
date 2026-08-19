ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG GO_BUILD_FLAGS=-p=1
ARG QWQ_ARTIFACT_ENVIRONMENT
ARG QWQ_ARTIFACT_CONFIG_DIGEST

FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG QWQ_PROVIDER_BINDING_MANIFEST_DIGEST
ARG TARGETOS
ARG TARGETARCH
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /build
COPY go.mod go.sum ./
RUN --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    go mod download
COPY . .
RUN --mount=type=cache,id=quwoquan-go-build,target=/root/.cache/go-build \
    --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    --mount=type=bind,from=qwq_provider_bindings,source=.,target=/run/qwq-provider-bindings,ro \
    test -n "${QWQ_PROVIDER_BINDING_MANIFEST_DIGEST}" \
    && CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build -overlay=/run/qwq-provider-bindings/go.overlay.json ${GO_BUILD_FLAGS} \
    -o /product-ops-service ./services/product-ops-service/cmd/api

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
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
      fi; \
      if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
      fi; \
      apt-get update \
      && apt-get install -y --no-install-recommends ca-certificates tzdata \
      && rm -rf /var/lib/apt/lists/*; \
    fi
COPY --from=builder /product-ops-service /usr/local/bin/product-ops-service
EXPOSE 18086
CMD ["product-ops-service"]
