package runtimeobservability

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

const w3cExampleTraceID = "4bf92f3577b34da6a3ce929d0e0e4736"

func TestHTTPMiddlewareExtractsTraceparent(t *testing.T) {
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	captured := make(chan string, 1)
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		meta, ok := CorrelationMetaFromContext(r.Context())
		if ok {
			captured <- meta.TraceID
		} else {
			captured <- ""
		}
		w.WriteHeader(http.StatusOK)
	})

	ioLogger, processLogger, exceptionLogger := newTestLoggers(t)

	handler := NewHTTPServerMiddleware(inner, HTTPServerMiddlewareConfig{
		Service: "test-svc",
		Origin:  "test",
	}, ioLogger, processLogger, exceptionLogger)

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("traceparent", "00-"+w3cExampleTraceID+"-00f067aa0ba902b7-01")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	traceID := <-captured
	if traceID == "" {
		t.Fatal("expected non-empty traceID from context")
	}
	if traceID != w3cExampleTraceID {
		t.Errorf("expected traceID %q from W3C trace context, got %q", w3cExampleTraceID, traceID)
	}
}

func TestOutboundInjectsTraceparent(t *testing.T) {
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
	))

	req := httptest.NewRequest("GET", "http://example.com/api", nil)

	otel.GetTextMapPropagator().Inject(req.Context(), propagation.HeaderCarrier(req.Header))
}
