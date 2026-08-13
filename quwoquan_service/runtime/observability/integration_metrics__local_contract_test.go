package runtimeobservability

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus/promhttp"
)

func TestMetricsScrapeIntegration(t *testing.T) {
	app := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	})

	ioLogger, processLogger, exceptionLogger := newTestLoggers(t)

	wrapped := NewHTTPServerMiddleware(app, HTTPServerMiddlewareConfig{
		Service: "integration-test-svc",
		Origin:  "test",
	}, ioLogger, processLogger, exceptionLogger)

	mux := http.NewServeMux()
	mux.Handle("/api/test", wrapped)
	mux.Handle("/metrics", promhttp.Handler())

	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	for range 5 {
		resp, err := http.Get(server.URL + "/api/test")
		if err != nil {
			t.Fatalf("request failed: %v", err)
		}
		_ = resp.Body.Close()
	}

	resp, err := http.Get(server.URL + "/metrics")
	if err != nil {
		t.Fatalf("metrics scrape failed: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read metrics body: %v", err)
	}
	metricsOutput := string(body)

	expectedMetrics := []string{
		"http_server_requests_total",
		"http_server_duration_seconds",
		"http_server_inflight_requests",
		"http_server_response_bytes",
	}
	for _, m := range expectedMetrics {
		if !strings.Contains(metricsOutput, m) {
			t.Errorf("expected metric %q in /metrics output", m)
		}
	}

	if !strings.Contains(metricsOutput, "integration-test-svc") {
		t.Error("expected service label 'integration-test-svc' in metrics output")
	}
}
