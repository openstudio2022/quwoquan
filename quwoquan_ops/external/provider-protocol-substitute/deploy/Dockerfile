ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
FROM ${GO_BASE_IMAGE} AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -o /out/provider-protocol-substitute ./cmd/provider-protocol-substitute

FROM ${ALPINE_BASE_IMAGE}
RUN addgroup -S qwq && adduser -S -G qwq qwq
COPY --from=build /out/provider-protocol-substitute /usr/local/bin/provider-protocol-substitute
USER qwq
EXPOSE 18089
ENTRYPOINT ["/usr/local/bin/provider-protocol-substitute"]
