package servicekit

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"

	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
)

// ObservabilityStack 是一个服务模块的标准观测栈：OTel tracer、
// stdout/stderr 双通道 runtime log 上云与三类结构化日志器。
type ObservabilityStack struct {
	IOLogger        *robs.IOAccessLogger
	ProcessLogger   *robs.ProcessTraceLogger
	ExceptionLogger *robs.ExceptionLogger

	shutdowns []func()
}

// NewObservabilityStack 装配观测栈。exporter 端点由部署面通过
// RUNTIME_LOG_INGEST_URL/RUNTIME_LOG_INGEST_TOKEN/RUNTIME_LOG_SPOOL_DIR 注入，
// 未配置时仅 stdout；推送失败静默降级，不影响业务链路。
//
// kvFilter 决定进程 trace 的 input/output KV 元数据处置：nil 表示原样记录，
// 传入 filter 则按其策略脱敏（空策略即完全不记录 KV）。处理凭据、令牌一类
// 敏感载荷的服务必须显式传入 filter。
func NewObservabilityStack(
	identity Identity,
	kvFilter *robs.KVMetadataFilter,
) (*ObservabilityStack, error) {
	stack := &ObservabilityStack{}

	otelShutdown := rtotel.MustInit(rtotel.Config{
		ServiceName:   identity.ServiceName,
		SamplingRatio: 0.1,
	})
	stack.shutdowns = append(stack.shutdowns, otelShutdown)

	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		stack.Close()
		return nil, fmt.Errorf("%s runtime log exporter init failed: %w", identity.ServiceName, err)
	}
	stack.shutdowns = append(stack.shutdowns, runtimeLogExporter.Close)

	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	stack.shutdowns = append(stack.shutdowns, func() {
		errorLogWriter.Close()
		standardLogWriter.Close()
	})

	stack.IOLogger = robs.NewIOAccessLogger(standardLogWriter)
	stack.ProcessLogger, err = robs.NewProcessTraceLogger(
		standardLogWriter, errorLogWriter, "info", kvFilter,
	)
	if err != nil {
		stack.Close()
		return nil, fmt.Errorf("%s process logger init failed: %w", identity.ServiceName, err)
	}
	stack.ExceptionLogger, err = robs.NewExceptionLogger(standardLogWriter, errorLogWriter, kvFilter)
	if err != nil {
		stack.Close()
		return nil, fmt.Errorf("%s exception logger init failed: %w", identity.ServiceName, err)
	}
	return stack, nil
}

// WrapHTTPHandler 把 handler 接入 IO 访问日志、进程 trace 与异常日志中间件。
// Origin/Direction/SourceID/Src 是服务入站 HTTP 的固定语义，统一由本包填充，
// 不再由各服务重复声明。
//
// endpointResolver 把具体请求路径归一为 contract 的 operation path template，
// 使观测面的 endpoint 维度与 ContractGraph 同源、基数有界；nil 表示按原始
// 路径记录。
func (stack *ObservabilityStack) WrapHTTPHandler(
	handler http.Handler,
	identity Identity,
	endpointResolver func(*http.Request) string,
) http.Handler {
	return rthttp.NewHTTPServerMiddleware(handler, rthttp.HTTPServerMiddlewareConfig{
		Service:           identity.ServiceName,
		ServiceName:       identity.ServiceName,
		ServiceInstanceID: identity.InstanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          identity.ServiceName,
		Src:               identity.ServiceName,
		EndpointResolver:  endpointResolver,
	}, stack.IOLogger, stack.ProcessLogger, stack.ExceptionLogger)
}

// Close 逆序释放观测栈资源；幂等。
func (stack *ObservabilityStack) Close() {
	for index := len(stack.shutdowns) - 1; index >= 0; index-- {
		stack.shutdowns[index]()
	}
	stack.shutdowns = nil
}

// CleanupFunc 以 servicehost cleanup 栈约定包装 Close。
func (stack *ObservabilityStack) CleanupFunc() func(context.Context) error {
	return func(context.Context) error {
		stack.Close()
		return nil
	}
}
