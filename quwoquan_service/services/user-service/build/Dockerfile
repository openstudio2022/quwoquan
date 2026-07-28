ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
ARG ALPINE_PACKAGE_REPOSITORY=https://mirrors.aliyun.com/alpine
ARG GO_BUILD_FLAGS=-p=1

FROM ${GO_BASE_IMAGE} AS builder
ARG GO_BUILD_FLAGS
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    go mod download
COPY . .
RUN --mount=type=cache,id=quwoquan-go-build,target=/root/.cache/go-build \
    --mount=type=cache,id=quwoquan-go-mod,target=/go/pkg/mod \
    CGO_ENABLED=0 GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB \
    go build ${GO_BUILD_FLAGS} -o /user-service ./services/user-service/cmd/api/

FROM ${ALPINE_BASE_IMAGE}
ARG ALPINE_PACKAGE_REPOSITORY
RUN if command -v apk >/dev/null 2>&1; then \
      test -n "${ALPINE_PACKAGE_REPOSITORY}" \
      && alpine_branch="$(. /etc/os-release && printf '%s' "${VERSION_ID%.*}")" \
      && printf '%s/%s/main\n%s/%s/community\n' \
        "${ALPINE_PACKAGE_REPOSITORY}" "v${alpine_branch}" \
        "${ALPINE_PACKAGE_REPOSITORY}" "v${alpine_branch}" > /etc/apk/repositories \
      && \
      apk add --no-cache ca-certificates tzdata; \
    else \
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
      fi; \
      if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
      fi; \
      apt-get update \
      && apt-get install -y --no-install-recommends ca-certificates tzdata \
      && rm -rf /var/lib/apt/lists/*; \
    fi
WORKDIR /app
COPY --from=builder /user-service /usr/local/bin/user-service
COPY --from=builder /src/services/user-service/resources/ /app/resources/
# LoadDefaultShardDirectory 从 cwd 解析 contracts/.../shard_directory.yaml（契约入镜，禁止运行时缺文件）。
COPY --from=builder /src/services/user-service/contracts/account/user_account/shard_directory.yaml \
    /app/contracts/account/user_account/shard_directory.yaml
EXPOSE 18081
ENTRYPOINT ["user-service"]
