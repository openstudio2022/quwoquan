ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG ALPINE_PACKAGE_REPOSITORY=https://mirrors.aliyun.com/alpine
ARG GO_BUILD_FLAGS=-p=1
ARG QWQ_ARTIFACT_ENVIRONMENT
ARG QWQ_ARTIFACT_CONFIG_DIGEST
ARG IP2REGION_DATA_VERSION=v3.17.0+incompatible
ARG IP2REGION_V4_SHA256=6307a9696f5711f84bcb8b25f07894de68a64a0ed4a1cc7e990562dd3084f210
ARG IP2REGION_V6_SHA256=5b93da35ac28bc316dccc54a758381f7a874ae0461dd51ff5df5e34815586f11

FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG QWQ_PROVIDER_BINDING_MANIFEST_DIGEST
ARG TARGETOS
ARG TARGETARCH
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ARG IP2REGION_DATA_VERSION
ARG IP2REGION_V4_SHA256
ARG IP2REGION_V6_SHA256
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod go mod download
RUN --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    go mod download "github.com/lionsoul2014/ip2region@${IP2REGION_DATA_VERSION}" \
    && IP2REGION_DIR="$(go env GOMODCACHE)/github.com/lionsoul2014/ip2region@${IP2REGION_DATA_VERSION}" \
    && echo "${IP2REGION_V4_SHA256}  ${IP2REGION_DIR}/data/ip2region_v4.xdb" | sha256sum -c - \
    && echo "${IP2REGION_V6_SHA256}  ${IP2REGION_DIR}/data/ip2region_v6.xdb" | sha256sum -c - \
    && install -d /geoip /geoip-license \
    && install -m 0444 "${IP2REGION_DIR}/data/ip2region_v4.xdb" /geoip/ip2region_v4.xdb \
    && install -m 0444 "${IP2REGION_DIR}/data/ip2region_v6.xdb" /geoip/ip2region_v6.xdb \
    && install -m 0444 "${IP2REGION_DIR}/LICENSE.md" /geoip-license/LICENSE.md
COPY . .
RUN --mount=type=cache,id=quwoquan-go-build,target=/root/.cache/go-build \
    --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    --mount=type=bind,from=qwq_provider_bindings,source=.,target=/run/qwq-provider-bindings,ro \
    test -n "${QWQ_PROVIDER_BINDING_MANIFEST_DIGEST}" \
    && CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build -overlay=/run/qwq-provider-bindings/go.overlay.json ${GO_BUILD_FLAGS} -trimpath -ldflags="-s -w" \
    -o /out/service-core \
    ./cmd/service-core

FROM ${ALPINE_BASE_IMAGE}
ARG ALPINE_PACKAGE_REPOSITORY
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
      test -n "${ALPINE_PACKAGE_REPOSITORY}" \
      && alpine_branch="$(. /etc/os-release && printf '%s' "${VERSION_ID%.*}")" \
      && printf '%s/%s/main\n%s/%s/community\n' \
        "${ALPINE_PACKAGE_REPOSITORY}" "v${alpine_branch}" \
        "${ALPINE_PACKAGE_REPOSITORY}" "v${alpine_branch}" > /etc/apk/repositories \
      && apk add --no-cache ca-certificates tzdata ffmpeg; \
    else \
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
      fi; \
      if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
      fi; \
      apt-get update \
      && apt-get install -y --no-install-recommends ca-certificates tzdata ffmpeg \
      && rm -rf /var/lib/apt/lists/*; \
    fi
WORKDIR /app
COPY --from=builder /out/service-core /usr/local/bin/service-core
COPY --from=builder /geoip/ /etc/quwoquan/geoip/
COPY --from=builder /geoip-license/ /usr/share/licenses/ip2region/
COPY --from=builder /src/services/assistant-service/resources/ /app/resources/
COPY --from=builder /src/services/content-service/resources/ /app/resources/
COPY --from=builder /src/services/user-service/resources/ /app/resources/
COPY --from=builder /src/services/user-service/contracts/account/user_account/shard_directory.yaml \
    /app/contracts/account/user_account/shard_directory.yaml
ENV CONTENT_GEOIP_V4_DB_PATH=/etc/quwoquan/geoip/ip2region_v4.xdb
ENV CONTENT_GEOIP_V6_DB_PATH=/etc/quwoquan/geoip/ip2region_v6.xdb
EXPOSE 18079 18080 18081 18082 18084 18086 18087 18092 18095
ENTRYPOINT ["/usr/local/bin/service-core"]
