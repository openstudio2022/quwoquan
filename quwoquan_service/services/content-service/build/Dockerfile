# Multi-stage build for content-service
# Build context: quwoquan_service/

ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG ALPINE_PACKAGE_REPOSITORY=https://mirrors.aliyun.com/alpine
ARG GO_BUILD_FLAGS=-p=1
ARG IP2REGION_DATA_VERSION=v3.17.0+incompatible
ARG IP2REGION_V4_SHA256=6307a9696f5711f84bcb8b25f07894de68a64a0ed4a1cc7e990562dd3084f210
ARG IP2REGION_V6_SHA256=5b93da35ac28bc316dccc54a758381f7a874ae0461dd51ff5df5e34815586f11

FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG TARGETOS
ARG TARGETARCH
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ARG IP2REGION_DATA_VERSION
ARG IP2REGION_V4_SHA256
ARG IP2REGION_V6_SHA256
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /build
COPY go.mod go.sum ./
RUN --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    go mod download
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
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /content-service ./services/content-service/cmd/api/

# ffmpeg/ffprobe 是 media-processing worker（UGC 视频转码/封面/预览轨道）的
# 硬依赖；缺失时服务启动 fail-fast。
FROM ${ALPINE_BASE_IMAGE}
ARG ALPINE_PACKAGE_REPOSITORY
RUN if command -v apk >/dev/null 2>&1; then \
      test -n "${ALPINE_PACKAGE_REPOSITORY}" \
      && alpine_branch="$(. /etc/os-release && printf '%s' "${VERSION_ID%.*}")" \
      && printf '%s/%s/main\n%s/%s/community\n' \
        "${ALPINE_PACKAGE_REPOSITORY}" "v${alpine_branch}" \
        "${ALPINE_PACKAGE_REPOSITORY}" "v${alpine_branch}" > /etc/apk/repositories \
      && \
      apk add --no-cache ca-certificates tzdata ffmpeg; \
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
    fi \
    && command -v ffmpeg >/dev/null 2>&1 \
    && command -v ffprobe >/dev/null 2>&1
COPY --from=builder /content-service /usr/local/bin/content-service
COPY --from=builder /geoip/ /etc/quwoquan/geoip/
COPY --from=builder /geoip-license/ /usr/share/licenses/ip2region/
COPY services/content-service/resources/ /app/resources/
ENV QWQ_SEGMENTS_PATH=/app/resources/policies/content/post/recommendation_segments.yaml
ENV QWQ_REC_POLICY_PATH=/app/resources/policies/content/post/recommendation_policy.yaml
EXPOSE 18080
CMD ["content-service"]
