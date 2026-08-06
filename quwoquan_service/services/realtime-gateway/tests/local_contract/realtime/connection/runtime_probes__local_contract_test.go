// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-001
// readiness_case: health-check-local
// readiness_case: readiness-check-local
// readiness_case: metrics-local
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rthealth "quwoquan_service/runtime/health"
	httpadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/http"
)

func TestConnectionRuntimeProbeRoutesExposeTypedHealthReadinessAndMetrics(
	t *testing.T,
) {
	checker := rthealth.NewChecker()
	checker.Register("realtime_redis", func(context.Context) error { return nil })
	mux := http.NewServeMux()
	metrics := http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusOK)
		_, _ = writer.Write([]byte("realtime_connection_sessions 1\n"))
	})
	if err := httpadapter.RegisterRuntimeProbeRoutes(mux, checker, metrics); err != nil {
		t.Fatal(err)
	}

	for path, wantBody := range map[string]string{
		"/healthz": `"status":"ok"`,
		"/readyz":  `"status":"ready"`,
		"/metrics": "realtime_connection_sessions 1",
	} {
		response := httptest.NewRecorder()
		mux.ServeHTTP(response, httptest.NewRequest(http.MethodGet, path, nil))
		if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), wantBody) {
			t.Fatalf("GET %s status=%d body=%s", path, response.Code, response.Body.String())
		}
	}

	degraded := rthealth.NewChecker()
	degraded.Register("realtime_redis", func(context.Context) error {
		return errors.New("redis unavailable")
	})
	degradedMux := http.NewServeMux()
	if err := httpadapter.RegisterRuntimeProbeRoutes(degradedMux, degraded, metrics); err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	request.Header.Set("X-Request-Id", "realtime-probe-contract")
	response := httptest.NewRecorder()
	degradedMux.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable ||
		!strings.Contains(response.Body.String(), `"code":"REALTIME.SYSTEM.readiness_unavailable"`) ||
		strings.Contains(response.Body.String(), "redis unavailable") {
		t.Fatalf("degraded readiness status=%d body=%s", response.Code, response.Body.String())
	}
}
