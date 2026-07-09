# Multi-stage build for entity-service
# Build context: quwoquan_service/
# entity-service is its own Go module (replace quwoquan_service => ../..),
# so the parent module must be present in the build context, mirroring how
# seed-box builds integration-service.

ARG GO_BASE_IMAGE=golang:1.24-bookworm
ARG ALPINE_BASE_IMAGE=alpine:3.19
ARG GO_BUILD_FLAGS=-p=1

FROM ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /build
COPY go.mod go.sum ./
COPY services/entity-service/go.mod services/entity-service/go.sum ./services/entity-service/
RUN go mod download && \
    cd services/entity-service && go mod download
COPY . .
RUN cd services/entity-service && \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /entity-service ./cmd/api/

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
COPY --from=builder /entity-service /usr/local/bin/entity-service
COPY services/entity-service/configs/ /etc/entity-service/
EXPOSE 18084
CMD ["entity-service"]
