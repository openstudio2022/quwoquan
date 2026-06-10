ARG GO_BASE_IMAGE=golang:1.24-bookworm
ARG ALPINE_BASE_IMAGE=alpine:3.19
ARG GO_BUILD_FLAGS=-p=1

FROM ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /user-service ./services/user-service/cmd/api/

FROM ${ALPINE_BASE_IMAGE}
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /user-service /usr/local/bin/user-service
COPY --from=builder /src/services/user-service/internal/infrastructure/migration /etc/migration
EXPOSE 18081
ENTRYPOINT ["user-service"]
