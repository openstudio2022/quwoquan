# Multi-stage build for content-service
# Build context: quwoquan_service/

ARG GO_BASE_IMAGE=golang:1.24-bookworm
ARG ALPINE_BASE_IMAGE=alpine:3.19

FROM ${GO_BASE_IMAGE} AS builder
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /content-service ./services/content-service/cmd/api/

FROM ${ALPINE_BASE_IMAGE}
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /content-service /usr/local/bin/content-service
COPY services/content-service/configs/ /etc/content-service/
EXPOSE 18080
CMD ["content-service"]
