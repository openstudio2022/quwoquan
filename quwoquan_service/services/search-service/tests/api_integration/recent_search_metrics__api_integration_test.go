package api_integration

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtmetrics "quwoquan_service/runtime/metrics"
	httpadapter "quwoquan_service/services/search-service/internal/adapters/http"
	"quwoquan_service/services/search-service/internal/infrastructure/searchmetrics"
)

func TestRecentSearchRoutePublishesBoundedPrometheusMetrics(t *testing.T) {
	mux := http.NewServeMux()
	httpadapter.NewRecentSearchHandler(
		nil,
		searchmetrics.NewRecorder(),
	).Register(mux)
	mux.Handle("/metrics", rtmetrics.Handler())

	recentResponse := httptest.NewRecorder()
	mux.ServeHTTP(
		recentResponse,
		httptest.NewRequest(http.MethodGet, "/search/recent", nil),
	)
	if recentResponse.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous recent search must fail closed with 401, got %d", recentResponse.Code)
	}

	metricsResponse := httptest.NewRecorder()
	mux.ServeHTTP(
		metricsResponse,
		httptest.NewRequest(http.MethodGet, "/metrics", nil),
	)
	if metricsResponse.Code != http.StatusOK {
		t.Fatalf("metrics endpoint status=%d", metricsResponse.Code)
	}
	body := metricsResponse.Body.String()
	for _, fragment := range []string{
		`search_recent_requests_total{operation="list",status="unauthorized"}`,
		`search_recent_duration_seconds_count{operation="list",status="unauthorized"}`,
	} {
		if !strings.Contains(body, fragment) {
			t.Fatalf("metrics endpoint missing %q", fragment)
		}
	}
}
