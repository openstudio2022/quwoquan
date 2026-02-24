package runtimehttp

import (
	"context"
	"net/http"

	robs "quwoquan_service/runtime/observability"
)

type CorrelationMeta = robs.CorrelationMeta
type EndpointMeta = robs.EndpointMeta

type HTTPServerMiddlewareConfig = robs.HTTPServerMiddlewareConfig
type HTTPClientMiddlewareConfig = robs.HTTPClientMiddlewareConfig
type HTTPClientFactoryConfig = robs.HTTPClientFactoryConfig
type LoggedRoundTripper = robs.LoggedRoundTripper

func WithCorrelationMeta(ctx context.Context, meta CorrelationMeta) context.Context {
	return robs.WithCorrelationMeta(ctx, meta)
}

func CorrelationMetaFromContext(ctx context.Context) (CorrelationMeta, bool) {
	return robs.CorrelationMetaFromContext(ctx)
}

func NewHTTPServerMiddleware(
	next http.Handler,
	cfg HTTPServerMiddlewareConfig,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) http.Handler {
	return robs.NewHTTPServerMiddleware(next, cfg, ioLogger, processLogger, exceptionLogger)
}

func NewLoggedRoundTripper(
	base http.RoundTripper,
	cfg HTTPClientMiddlewareConfig,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) *LoggedRoundTripper {
	return robs.NewLoggedRoundTripper(base, cfg, ioLogger, processLogger, exceptionLogger)
}

func DefaultHTTPClientFactoryConfig() HTTPClientFactoryConfig {
	return robs.DefaultHTTPClientFactoryConfig()
}

func NewObservedHTTPClient(
	baseTransport http.RoundTripper,
	factoryCfg HTTPClientFactoryConfig,
	logCfg HTTPClientMiddlewareConfig,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) *http.Client {
	return robs.NewObservedHTTPClient(baseTransport, factoryCfg, logCfg, ioLogger, processLogger, exceptionLogger)
}

func NewGatewayClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewGatewayClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}

func NewOrchestratorClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewOrchestratorClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}

func NewContentClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewContentClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}

func NewCircleClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewCircleClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}

func NewUserClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewUserClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}

func NewChatClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewChatClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}

func NewAssistantClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewAssistantClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}

func NewProductOpsClient(baseTransport http.RoundTripper, ioLogger *robs.IOAccessLogger, processLogger *robs.ProcessTraceLogger, exceptionLogger *robs.ExceptionLogger) *http.Client {
	return robs.NewProductOpsClient(baseTransport, ioLogger, processLogger, exceptionLogger)
}
