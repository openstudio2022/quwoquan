FROM golang:1.24-alpine AS builder

WORKDIR /build

COPY go.mod go.sum ./
COPY runtime/ runtime/
COPY services/circle-service/ services/circle-service/

RUN cd services/circle-service && go build -o /circle-service ./cmd/api

FROM alpine:3.21

RUN apk --no-cache add ca-certificates tzdata
COPY --from=builder /circle-service /usr/local/bin/circle-service
COPY services/circle-service/configs/ /app/configs/

ENV APP_ENV=integration
ENV SERVICE_NAME=circle-service

WORKDIR /app
EXPOSE 18082

ENTRYPOINT ["circle-service"]
