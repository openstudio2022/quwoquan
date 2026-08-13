ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG GO_BUILD_FLAGS=-p=1

FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG TARGETOS
ARG TARGETARCH

WORKDIR /build

COPY go.mod go.sum ./
RUN --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    go mod download
COPY . .

RUN --mount=type=cache,id=quwoquan-go-build,target=/root/.cache/go-build \
    --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build ${GO_BUILD_FLAGS} -o /circle-service ./services/circle-service/cmd/standalone-api

FROM ${ALPINE_BASE_IMAGE}

RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /circle-service /usr/local/bin/circle-service

ENV APP_ENV=integration
ENV SERVICE_NAME=circle-service

WORKDIR /app
EXPOSE 18082

ENTRYPOINT ["circle-service"]
