# Multi-stage build for rtc-service
# Build context: quwoquan_service/

ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG GO_BUILD_FLAGS=-p=1

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
    -o /rtc-service ./services/rtc-service/cmd/api/

# 环境身份不烤入镜像：artifact-identity.json 由部署面挂载（DEC-005 信任域裁决），
# 启动时经 QWQ_ARTIFACT_IDENTITY_FILE 读取并用 APP_ENV 断言校验。
FROM ${ALPINE_BASE_IMAGE}
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /rtc-service /usr/local/bin/rtc-service
EXPOSE 18083
CMD ["rtc-service"]
