package runtimeobservability

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus/promhttp"
)

func TestContentConsumptionJourneyMetrics(t *testing.T) {
	ioLogger, processLogger, exceptionLogger := newTestLoggers(t)

	feedHandler := NewHTTPServerMiddleware(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"items":[]}`))
		}),
		HTTPServerMiddlewareConfig{Service: "content-service", Origin: "test"},
		ioLogger, processLogger, exceptionLogger,
	)

	detailHandler := NewHTTPServerMiddleware(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"id":"post-1"}`))
		}),
		HTTPServerMiddlewareConfig{Service: "content-service", Origin: "test"},
		ioLogger, processLogger, exceptionLogger,
	)

	interactionHandler := NewHTTPServerMiddleware(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
		HTTPServerMiddlewareConfig{Service: "content-service", Origin: "test"},
		ioLogger, processLogger, exceptionLogger,
	)

	mux := http.NewServeMux()
	mux.Handle("/content/feed", feedHandler)
	mux.Handle("/content/content/posts/post-1", detailHandler)
	mux.Handle("/content/interactions/like", interactionHandler)
	mux.Handle("/metrics", promhttp.Handler())

	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	steps := []struct {
		method string
		path   string
	}{
		{"GET", "/content/feed"},
		{"GET", "/content/content/posts/post-1"},
		{"POST", "/content/interactions/like"},
	}

	for _, step := range steps {
		req, err := http.NewRequest(step.method, server.URL+step.path, nil)
		if err != nil {
			t.Fatalf("build request: %v", err)
		}
		req.Header.Set("X-Client-Session-Id", "test-session-1")
		req.Header.Set("X-Client-User-Id", "user-1")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatalf("%s %s failed: %v", step.method, step.path, err)
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

	journeyEndpoints := []string{
		"/content/feed",
		"/content/content/posts/post-1",
		"/content/interactions/like",
	}
	for _, ep := range journeyEndpoints {
		if !strings.Contains(metricsOutput, ep) {
			t.Errorf("expected journey endpoint %q in metrics output", ep)
		}
	}

	if !strings.Contains(metricsOutput, `service="content-service"`) {
		t.Error("expected service=content-service in metrics")
	}
}
