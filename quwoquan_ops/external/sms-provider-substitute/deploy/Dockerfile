ARG GO_BASE_IMAGE
ARG ALPINE_BASE_IMAGE
FROM ${GO_BASE_IMAGE} AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -o /out/sms-provider-substitute ./cmd/sms-provider-substitute

FROM ${ALPINE_BASE_IMAGE}
RUN addgroup -S qwq && adduser -S -G qwq qwq
COPY --from=build /out/sms-provider-substitute /usr/local/bin/sms-provider-substitute
USER qwq
EXPOSE 9443
ENTRYPOINT ["/usr/local/bin/sms-provider-substitute"]
