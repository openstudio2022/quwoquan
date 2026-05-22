package runtimeobservability

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const instrumentationName = "quwoquan_service/runtime/observability"

func Tracer() trace.Tracer {
	return otel.Tracer(instrumentationName)
}

// StartBusinessSpan starts a span for a business journey, attaching correlation
// metadata from context if available.
func StartBusinessSpan(ctx context.Context, spanName string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	ctx, span := Tracer().Start(ctx, spanName, trace.WithAttributes(attrs...))
	if meta, ok := CorrelationMetaFromContext(ctx); ok {
		span.SetAttributes(
			attribute.String("session.id", meta.SessionID),
			attribute.String("user.id", meta.UserID),
			attribute.String("request.id", meta.RequestID),
			attribute.String("trace.id", meta.TraceID),
		)
	}
	return ctx, span
}

// EndSpan ends a span, recording any error.
func EndSpan(span trace.Span, err error) {
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
	}
	span.End()
}
