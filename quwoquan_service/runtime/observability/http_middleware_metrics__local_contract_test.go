package runtimeobservability

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func newTestLoggers(t *testing.T) (*IOAccessLogger, *ProcessTraceLogger, *ExceptionLogger) {
	t.Helper()
	ioLogger := NewIOAccessLogger(io.Discard)
	processLogger, err := NewProcessTraceLogger(io.Discard, io.Discard, "info", nil)
	if err != nil {
		t.Fatal(err)
	}
	exceptionLogger, err := NewExceptionLogger(io.Discard, io.Discard, nil)
	if err != nil {
		t.Fatal(err)
	}
	return ioLogger, processLogger, exceptionLogger
}

func TestHTTPMiddlewareProducesMetrics(t *testing.T) {
	ioLogger, processLogger, exceptionLogger := newTestLoggers(t)

	handler := NewHTTPServerMiddleware(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{"ok":true}`))
		}),
		HTTPServerMiddlewareConfig{
			Service: "test-svc",
			Origin:  "test",
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)

	req := httptest.NewRequest("GET", "/api/test", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	val := testutil.ToFloat64(httpRequestsTotal.WithLabelValues("test-svc", "/api/test", "GET", "200"))
	if val != 1 {
		t.Errorf("http_server_requests_total: expected 1, got %v", val)
	}

	latencyCount := testutil.CollectAndCount(httpDurationSeconds)
	if latencyCount == 0 {
		t.Error("http_server_duration_seconds should have at least one metric")
	}
}

func TestHTTPMiddleware4xxCountsErrorCode(t *testing.T) {
	ioLogger, processLogger, exceptionLogger := newTestLoggers(t)

	handler := NewHTTPServerMiddleware(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusNotFound)
			w.Write([]byte(`{"code":"CONTENT.VALIDATION.not_found","userMessage":"未找到"}`))
		}),
		HTTPServerMiddlewareConfig{
			Service: "test-svc-4xx",
			Origin:  "test",
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)

	req := httptest.NewRequest("GET", "/api/missing", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}

	val := testutil.ToFloat64(httpErrorCodesTotal.WithLabelValues(
		"test-svc-4xx", "CONTENT.VALIDATION.not_found", "CONTENT", "VALIDATION"))
	if val != 1 {
		t.Errorf("http_server_error_codes_total: expected 1, got %v", val)
	}
}
