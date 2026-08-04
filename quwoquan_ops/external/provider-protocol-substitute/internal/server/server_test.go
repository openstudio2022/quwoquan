package server

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const testOperatorToken = "provider-substitute-test-operator-token"

func canonicalTestSHA256(payload string) string {
	return fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(payload)))
}

func TestServerRejectsProdAndShortOperatorMaterial(t *testing.T) {
	if _, err := New(Config{
		Environment:         "prod",
		ConfigurationDigest: canonicalTestSHA256("provider-substitute:prod-config"),
		OperatorToken:       testOperatorToken,
	}); err == nil {
		t.Fatal("Prod must never start the non-production substitute")
	}
	if _, err := New(Config{
		Environment:         "alpha",
		ConfigurationDigest: canonicalTestSHA256("provider-substitute:alpha-config"),
		OperatorToken:       "short",
	}); err == nil {
		t.Fatal("short operator material must fail closed")
	}
}

func TestProtocolRoutesAndProtectedControlPlane(t *testing.T) {
	server := newTestServer(t)
	handler := server.Handler()

	health := httptest.NewRecorder()
	handler.ServeHTTP(health, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if health.Code != http.StatusOK || !strings.Contains(health.Body.String(), AdapterID) {
		t.Fatalf("health=%d %s", health.Code, health.Body.String())
	}

	model := httptest.NewRecorder()
	handler.ServeHTTP(
		model,
		httptest.NewRequest(
			http.MethodPost,
			"/v1/chat/completions",
			strings.NewReader(`{"messages":[{"role":"user","content":"hello"}]}`),
		),
	)
	if model.Code != http.StatusOK || !strings.Contains(model.Body.String(), "隔离协议替代链路") {
		t.Fatalf("model=%d %s", model.Code, model.Body.String())
	}

	location := httptest.NewRecorder()
	handler.ServeHTTP(
		location,
		httptest.NewRequest(
			http.MethodGet,
			"/map/place/v2/search?query=coffee&location=30.1,120.2",
			nil,
		),
	)
	if location.Code != http.StatusOK || !strings.Contains(location.Body.String(), "Nonprod Search POI") {
		t.Fatalf("location=%d %s", location.Code, location.Body.String())
	}

	unauthorized := httptest.NewRecorder()
	handler.ServeHTTP(
		unauthorized,
		httptest.NewRequest(http.MethodGet, "/control/receipts", nil),
	)
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("unprotected control plane status=%d", unauthorized.Code)
	}

	receipts := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/control/receipts", nil)
	request.Header.Set("Authorization", "Bearer "+testOperatorToken)
	handler.ServeHTTP(receipts, request)
	if receipts.Code != http.StatusOK ||
		!strings.Contains(receipts.Body.String(), "assistant.model.generation") ||
		strings.Contains(receipts.Body.String(), testOperatorToken) {
		t.Fatalf("receipts=%d %s", receipts.Code, receipts.Body.String())
	}
}

func TestFaultScenarioIsRemoteControlledAndRecoverable(t *testing.T) {
	server := newTestServer(t)
	handler := server.Handler()

	setScenario(t, handler, "throttle")
	throttled := httptest.NewRecorder()
	handler.ServeHTTP(
		throttled,
		httptest.NewRequest(http.MethodGet, "/weather/forecast", nil),
	)
	if throttled.Code != http.StatusTooManyRequests {
		t.Fatalf("throttled status=%d", throttled.Code)
	}

	setScenario(t, handler, "success")
	recovered := httptest.NewRecorder()
	handler.ServeHTTP(
		recovered,
		httptest.NewRequest(http.MethodGet, "/weather/forecast", nil),
	)
	if recovered.Code != http.StatusOK {
		t.Fatalf("recovered status=%d body=%s", recovered.Code, recovered.Body.String())
	}
}

func newTestServer(t *testing.T) *Server {
	t.Helper()
	server, err := New(Config{
		Environment:         "alpha",
		ConfigurationDigest: canonicalTestSHA256("provider-substitute:alpha-config"),
		OperatorToken:       testOperatorToken,
	})
	if err != nil {
		t.Fatal(err)
	}
	return server
}

func setScenario(t *testing.T, handler http.Handler, scenario string) {
	t.Helper()
	body, err := json.Marshal(map[string]string{"scenario": scenario})
	if err != nil {
		t.Fatal(err)
	}
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodPut,
		"/control/scenario",
		bytes.NewReader(body),
	)
	request.Header.Set("Authorization", "Bearer "+testOperatorToken)
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("set scenario=%s status=%d body=%s", scenario, recorder.Code, recorder.Body.String())
	}
}
