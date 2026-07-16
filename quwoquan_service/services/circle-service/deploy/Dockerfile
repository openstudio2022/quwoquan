FROM golang:1.24-alpine AS builder

WORKDIR /build

COPY go.mod go.sum ./
RUN go mod download
COPY . .

RUN go build -o /circle-service ./services/circle-service/cmd/api

FROM alpine:3.21

RUN apk --no-cache add ca-certificates tzdata
COPY --from=builder /circle-service /usr/local/bin/circle-service
COPY services/circle-service/configs/ /app/configs/

ENV APP_ENV=integration
ENV SERVICE_NAME=circle-service

WORKDIR /app
EXPOSE 18082

ENTRYPOINT ["circle-service"]
