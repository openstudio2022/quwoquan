# Multi-stage build for realtime-gateway
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
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /realtime-gateway ./services/realtime-gateway/cmd/api/

FROM ${ALPINE_BASE_IMAGE}
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /realtime-gateway /usr/local/bin/realtime-gateway
COPY services/realtime-gateway/configs/ /etc/realtime-gateway/
EXPOSE 18090
CMD ["realtime-gateway"]
