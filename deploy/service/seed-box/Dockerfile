ARG GO_BASE_IMAGE=golang:1.24-bookworm
ARG PYTHON_BASE_IMAGE=python:3.11-slim
ARG GO_BUILD_FLAGS=-p=1
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

FROM ${GO_BASE_IMAGE} AS go-builder
ARG GO_BUILD_FLAGS
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /build/quwoquan_service
COPY quwoquan_service/go.mod quwoquan_service/go.sum ./
RUN go mod download
COPY quwoquan_service/ ./
RUN mkdir -p /out/bin && \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
      go build ${GO_BUILD_FLAGS} -o /out/bin/content-service ./services/content-service/cmd/api && \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
      go build ${GO_BUILD_FLAGS} -o /out/bin/chat-service ./services/chat-service/cmd/api && \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
      go build ${GO_BUILD_FLAGS} -o /out/bin/user-service ./services/user-service/cmd/api && \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
      go build ${GO_BUILD_FLAGS} -o /out/bin/integration-service ./services/integration-service/cmd/api && \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
      go build ${GO_BUILD_FLAGS} -o /out/bin/circle-service ./services/circle-service/cmd/api

FROM ${PYTHON_BASE_IMAGE}
ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates tzdata && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8 \
    PIP_PROGRESS_BAR=off \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

COPY --from=go-builder /out/bin/ ./bin/
COPY deploy/service/seed-box/seed_box_entrypoint.py ./seed_box_entrypoint.py
COPY quwoquan_service/services/content-service/configs/ ./runtime-config/configs/content-service/
COPY quwoquan_service/services/chat-service/configs/ ./runtime-config/configs/chat-service/
COPY quwoquan_service/services/user-service/configs/ ./runtime-config/configs/user-service/
COPY quwoquan_service/services/integration-service/configs/ ./runtime-config/configs/integration-service/
COPY quwoquan_service/services/circle-service/configs/ ./runtime-config/configs/circle-service/
COPY releases/config/ ./runtime-config/releases/config/
COPY deploy/shared/ ./runtime-config/deploy/shared/
COPY quwoquan_service/contracts/metadata/ ./contracts/metadata/
COPY quwoquan_service/services/user-service/internal/infrastructure/migration/ ./services/user-service/internal/infrastructure/migration/

RUN mkdir -p /tmp/chat-media && chmod +x ./seed_box_entrypoint.py

EXPOSE 8080
CMD ["python3", "/app/seed_box_entrypoint.py"]
