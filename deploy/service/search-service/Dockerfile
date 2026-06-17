# Multi-stage build for search-service
# Build context: quwoquan_service/
# search-service 是独立 Go module（module quwoquan_service/services/search-service，
# replace quwoquan_service => ../..），与其它 root-module 服务不同：必须 COPY 整个
# quwoquan_service 源树，再从子模块目录构建，replace 的 ../.. 才能解析到父模块根。

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
COPY . .
WORKDIR /build/services/search-service
RUN go mod download
RUN CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /search-service ./cmd/api/

FROM ${ALPINE_BASE_IMAGE}
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /search-service /usr/local/bin/search-service
COPY services/search-service/configs/ /etc/search-service/
EXPOSE 18095
CMD ["search-service"]
