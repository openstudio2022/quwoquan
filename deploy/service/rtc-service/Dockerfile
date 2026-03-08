# Multi-stage build for rtc-service
# Build context: quwoquan_service/

FROM golang:1.22-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /rtc-service ./services/rtc-service/cmd/api/

FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /rtc-service /usr/local/bin/rtc-service
COPY services/rtc-service/configs/ /etc/rtc-service/
EXPOSE 18083
CMD ["rtc-service"]
