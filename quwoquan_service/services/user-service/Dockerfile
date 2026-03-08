FROM golang:1.24-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /user-service ./services/user-service/cmd/api/

FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /user-service /usr/local/bin/user-service
COPY --from=builder /src/services/user-service/internal/infrastructure/migration /etc/migration
EXPOSE 18081
ENTRYPOINT ["user-service"]
