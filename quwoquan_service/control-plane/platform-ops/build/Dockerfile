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
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /platform-ops-service ./control-plane/platform-ops/cmd/api

# 环境身份与环境配置树都不烤入镜像（DEC-005 信任域裁决）：
# artifact-identity.json 与单环境 runtime facts 树由部署面挂载，
# 启动时经 QWQ_ARTIFACT_IDENTITY_FILE 读取并用 APP_ENV 断言校验。
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
ENV REPO_ROOT=/app
EXPOSE 18088
CMD ["platform-ops-service"]
