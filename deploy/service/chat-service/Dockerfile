# Multi-stage build for chat-service
# Build context: quwoquan_service/

FROM golang:1.24.3-alpine AS builder
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /chat-service ./services/chat-service/cmd/api/

FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /chat-service /usr/local/bin/chat-service
COPY services/chat-service/configs/ /etc/chat-service/
EXPOSE 18082
CMD ["chat-service"]
