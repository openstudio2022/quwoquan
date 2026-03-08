# Multi-stage build for content-service
# Build context: quwoquan_service/

FROM golang:1.22-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /content-service ./services/content-service/cmd/api/

FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /content-service /usr/local/bin/content-service
COPY services/content-service/configs/ /etc/content-service/
EXPOSE 18080
CMD ["content-service"]
