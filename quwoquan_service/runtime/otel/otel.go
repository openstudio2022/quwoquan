package rtotel

import (
	"context"
	"fmt"
	"log/slog"
	"net/url"
	"os"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/exporters/stdout/stdouttrace"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

// Config holds initialisation options for the OTel trace pipeline.
type Config struct {
	ServiceName string
	// SamplingRatio controls the head-based sampling rate (0.0–1.0).
	// Default: 0.1 (10%).
	SamplingRatio float64
	// OTLPEndpoint sets the OTLP HTTP endpoint as an absolute URL
	// (e.g. "http://localhost:4318"). The scheme declares whether the
	// transport is encrypted and is required — see newExporter.
	// When empty, falls back to OTEL_EXPORTER_OTLP_ENDPOINT env var.
	// If neither is set, stdout exporter is used.
	OTLPEndpoint string
}

// MustInit sets up the global OTel TracerProvider and propagator.
// Returns a shutdown function that must be deferred by the caller.
//
// Exporter selection:
//   - If OTLPEndpoint or OTEL_EXPORTER_OTLP_ENDPOINT is set → OTLP/HTTP
//   - Otherwise → stdout (pretty-printed, for local dev)
//
// An invalid exporter declaration panics rather than degrading to a no-op
// provider: a rejected declaration that only logs would leave the service
// running with no traces and no way to tell that from a quiet service.
func MustInit(cfg Config) func() {
	if cfg.SamplingRatio <= 0 {
		cfg.SamplingRatio = 0.1
	}
	if cfg.ServiceName == "" {
		cfg.ServiceName = "quwoquan-service"
	}

	exporter, err := newExporter(cfg)
	if err != nil {
		panic(fmt.Sprintf("otel.MustInit: %v", err))
	}

	res, err := resource.Merge(
		resource.Default(),
		resource.NewSchemaless(
			attribute.String("service.name", cfg.ServiceName),
		),
	)
	if err != nil {
		slog.Error("otel resource init failed", "error", err)
		return func() {}
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.ParentBased(
			sdktrace.TraceIDRatioBased(cfg.SamplingRatio),
		)),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	return func() {
		if err := tp.Shutdown(context.Background()); err != nil {
			slog.Error("otel shutdown failed", "error", err)
		}
	}
}

// newExporter 构造 span exporter。
//
// 传输是否加密由 endpoint 的 URI scheme 声明，不按字符串形态猜。scheme 是 URI
// 契约的一部分，读它是解析声明而不是推断；缺 scheme 一律判否，避免「看起来像内网
// host:port 就明文发送」。改之前的判据是 HasPrefix(endpoint, "https")，而
// WithEndpoint 收的是 host:port，那个前缀永远不成立——明文是唯一可达分支，且没有
// 任何信号。
func newExporter(cfg Config) (sdktrace.SpanExporter, error) {
	endpoint := strings.TrimSpace(cfg.OTLPEndpoint)
	if endpoint == "" {
		endpoint = strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
	}
	if endpoint == "" {
		slog.Info("otel using stdout exporter (set OTEL_EXPORTER_OTLP_ENDPOINT for OTLP)")
		return stdouttrace.New(stdouttrace.WithPrettyPrint())
	}
	target, err := parseOTLPTarget(endpoint)
	if err != nil {
		return nil, err
	}
	opts := []otlptracehttp.Option{otlptracehttp.WithEndpoint(target.host)}
	if target.insecure {
		opts = append(opts, otlptracehttp.WithInsecure())
	}
	if target.urlPath != "" {
		opts = append(opts, otlptracehttp.WithURLPath(target.urlPath))
	}
	slog.Info(
		"otel using OTLP exporter",
		"endpoint", endpoint, "insecure", target.insecure,
	)
	return otlptracehttp.New(context.Background(), opts...)
}

// otlpTarget 是 endpoint URL 解析后的传输参数，insecure 直接来自声明的 scheme。
type otlpTarget struct {
	host     string
	urlPath  string
	insecure bool
}

func parseOTLPTarget(endpoint string) (otlpTarget, error) {
	parsed, err := url.Parse(endpoint)
	if err != nil {
		return otlpTarget{}, fmt.Errorf(
			"otel: OTLP endpoint %q is not a URL: %w", endpoint, err,
		)
	}
	target := otlpTarget{host: parsed.Host}
	switch parsed.Scheme {
	case "https":
	case "http":
		target.insecure = true
	default:
		return otlpTarget{}, fmt.Errorf(
			"otel: OTLP endpoint %q must declare its transport with an "+
				"http:// or https:// scheme", endpoint,
		)
	}
	if target.host == "" {
		return otlpTarget{}, fmt.Errorf(
			"otel: OTLP endpoint %q declares no host", endpoint,
		)
	}
	if strings.Trim(parsed.Path, "/") != "" {
		target.urlPath = parsed.Path
	}
	return target, nil
}
