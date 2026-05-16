package rtotel

import (
	"context"
	"log/slog"
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
	// OTLPEndpoint sets the OTLP HTTP endpoint (e.g. "localhost:4318").
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
func MustInit(cfg Config) func() {
	if cfg.SamplingRatio <= 0 {
		cfg.SamplingRatio = 0.1
	}
	if cfg.ServiceName == "" {
		cfg.ServiceName = "quwoquan-service"
	}

	exporter, err := newExporter(cfg)
	if err != nil {
		slog.Error("otel exporter init failed", "error", err)
		return func() {}
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

func newExporter(cfg Config) (sdktrace.SpanExporter, error) {
	endpoint := strings.TrimSpace(cfg.OTLPEndpoint)
	if endpoint == "" {
		endpoint = strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
	}
	if endpoint != "" {
		slog.Info("otel using OTLP exporter", "endpoint", endpoint)
		opts := []otlptracehttp.Option{
			otlptracehttp.WithEndpoint(endpoint),
		}
		if !strings.HasPrefix(endpoint, "https") {
			opts = append(opts, otlptracehttp.WithInsecure())
		}
		return otlptracehttp.New(context.Background(), opts...)
	}
	slog.Info("otel using stdout exporter (set OTEL_EXPORTER_OTLP_ENDPOINT for OTLP)")
	return stdouttrace.New(stdouttrace.WithPrettyPrint())
}
