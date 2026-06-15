# Multi-stage build for assistant-service
# Build context: quwoquan_service/

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
WORKDIR /build/services/assistant-service
RUN go mod download && \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=10 GOMEMLIMIT=1024MiB \
    go build ${GO_BUILD_FLAGS} -o /assistant-service ./cmd/api

FROM ${ALPINE_BASE_IMAGE}
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /assistant-service /usr/local/bin/assistant-service
COPY contracts/metadata/assistant/ /app/contracts/metadata/assistant/
COPY services/assistant-service/configs/ /etc/assistant-service/
EXPOSE 18087
CMD ["assistant-service"]
