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
WORKDIR /build
COPY go.mod go.sum ./
RUN --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    go mod download
COPY . .
RUN --mount=type=cache,id=quwoquan-go-build,target=/root/.cache/go-build \
    --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /integration-service ./services/integration-service/cmd/standalone-api/

FROM ${ALPINE_BASE_IMAGE}
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /integration-service /usr/local/bin/integration-service
WORKDIR /etc/integration-service
EXPOSE 18086
ENTRYPOINT ["integration-service"]
