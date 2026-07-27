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
    go build ${GO_BUILD_FLAGS} -o /product-ops-service ./services/product-ops-service/cmd/api

FROM ${ALPINE_BASE_IMAGE}
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
