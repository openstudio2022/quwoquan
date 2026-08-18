# Multi-stage build for rtc-service
# Build context: quwoquan_service/

ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG GO_BUILD_FLAGS=-p=1
ARG QWQ_ARTIFACT_ENVIRONMENT
ARG QWQ_ARTIFACT_CONFIG_DIGEST

FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
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
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /rtc-service ./services/rtc-service/cmd/api/

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
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /rtc-service /usr/local/bin/rtc-service
EXPOSE 18083
CMD ["rtc-service"]
