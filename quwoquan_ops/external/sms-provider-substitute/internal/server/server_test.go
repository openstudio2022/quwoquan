package server

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestRandomOTPIsCapturedOnceWithEnvironmentIsolation(t *testing.T) {
	now := time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC)
	s := newTestServer(t, now)
	payload := providerPayload(now.Add(5*time.Minute), "request-1", "+8618038139016", "482731")
	first := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", payload, "provider-token", map[string]string{
		"Idempotency-Key": "idem-1", "X-QWQ-Request-ID": "request-1",
	})
	if first.Code != http.StatusAccepted || strings.Contains(first.Body.String(), "482731") {
		t.Fatalf("unexpected provider response: %d %s", first.Code, first.Body.String())
	}
	s.mu.Lock()
	captured := s.captures[RecipientDigest("+8618038139016")]
	s.mu.Unlock()
	if strings.Contains(string(captured.Ciphertext), "482731") {
		t.Fatal("captured OTP was not encrypted")
	}
	metrics := perform(t, s.Handler(), http.MethodGet, "/metrics", nil, "", nil)
	if !strings.Contains(metrics.Body.String(), `adapter="ext.sms.local_capture"`) ||
		strings.Contains(metrics.Body.String(), "+8618038139016") ||
		strings.Contains(metrics.Body.String(), "482731") {
		t.Fatalf("metrics are incomplete or sensitive: %s", metrics.Body.String())
	}
	health := perform(t, s.Handler(), http.MethodGet, "/healthz", nil, "", nil)
	if !strings.Contains(health.Body.String(), `"configurationDigest":"sha256:`) ||
		!strings.Contains(health.Body.String(), `"nonPromotable":true`) {
		t.Fatalf("health readback is incomplete: %s", health.Body.String())
	}
	digest := RecipientDigest("+8618038139016")
	wrongEnv := perform(t, s.Handler(), http.MethodPost, "/v1/debug/sms/otp/latest", map[string]string{
		"environment": "beta", "recipientDigest": digest,
	}, "operator-token", nil)
	if wrongEnv.Code != http.StatusBadRequest {
		t.Fatalf("cross-environment read status=%d", wrongEnv.Code)
	}
	read := perform(t, s.Handler(), http.MethodPost, "/v1/debug/sms/otp/latest", map[string]string{
		"environment": "alpha", "recipientDigest": digest,
	}, "operator-token", nil)
	if read.Code != http.StatusOK || !strings.Contains(read.Body.String(), "482731") {
		t.Fatalf("protected read failed: %d %s", read.Code, read.Body.String())
	}
	secondRead := perform(t, s.Handler(), http.MethodPost, "/v1/debug/sms/otp/latest", map[string]string{
		"environment": "alpha", "recipientDigest": digest,
	}, "operator-token", nil)
	if secondRead.Code != http.StatusNotFound {
		t.Fatalf("OTP was not one-time: %d", secondRead.Code)
	}
}

func TestProviderRequestValidationAndCaptureTTL(t *testing.T) {
	current := time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC)
	s, err := New(Config{
		Environment: "alpha", ConfigurationDigest: "sha256:" + strings.Repeat("a", 64),
		ProviderToken: "provider-token", OperatorToken: "operator-token",
		CaptureKey: bytes.Repeat([]byte{7}, 32), Now: func() time.Time { return current },
	})
	if err != nil {
		t.Fatal(err)
	}

	invalidPhone := providerPayload(current.Add(time.Minute), "invalid-phone", "18038139016", "482731")
	response := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", invalidPhone, "provider-token", map[string]string{
		"Idempotency-Key": "invalid-phone", "X-QWQ-Request-ID": "invalid-phone",
	})
	if response.Code != http.StatusBadRequest {
		t.Fatalf("invalid phone status=%d", response.Code)
	}

	missingTemplate := providerPayload(current.Add(time.Minute), "missing-template", "+8618038139016", "482731")
	missingTemplate["payload"].(map[string]string)["templateId"] = ""
	response = perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", missingTemplate, "provider-token", map[string]string{
		"Idempotency-Key": "missing-template", "X-QWQ-Request-ID": "missing-template",
	})
	if response.Code != http.StatusBadRequest {
		t.Fatalf("missing template status=%d", response.Code)
	}

	valid := providerPayload(current.Add(time.Minute), "ttl-request", "+8618038139016", "482731")
	response = perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", valid, "provider-token", map[string]string{
		"Idempotency-Key": "ttl-request", "X-QWQ-Request-ID": "ttl-request",
	})
	if response.Code != http.StatusAccepted {
		t.Fatalf("valid request status=%d", response.Code)
	}
	current = current.Add(2 * time.Minute)
	read := perform(t, s.Handler(), http.MethodPost, "/v1/debug/sms/otp/latest", map[string]string{
		"environment": "alpha", "recipientDigest": RecipientDigest("+8618038139016"),
	}, "operator-token", nil)
	if read.Code != http.StatusNotFound {
		t.Fatalf("expired OTP was readable: %d", read.Code)
	}
	s.mu.Lock()
	remainingIdempotency := len(s.idempotency)
	s.mu.Unlock()
	if remainingIdempotency != 0 {
		t.Fatalf("expired idempotency records remain: %d", remainingIdempotency)
	}
}

func TestProviderAndOperatorCredentialsMustBeDistinct(t *testing.T) {
	_, err := New(Config{
		Environment: "alpha", ConfigurationDigest: "sha256:" + strings.Repeat("a", 64),
		ProviderToken: "same-token", OperatorToken: "same-token",
		CaptureKey: bytes.Repeat([]byte{7}, 32),
	})
	if err == nil {
		t.Fatal("identical provider and operator credentials were accepted")
	}
}

func TestAuthenticationIdempotencyTTLAndFailureScenes(t *testing.T) {
	now := time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC)
	s := newTestServer(t, now)
	payload := providerPayload(now.Add(time.Minute), "request-2", "+8613800000000", "927164")
	unauthorized := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", payload, "wrong", nil)
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("authentication status=%d", unauthorized.Code)
	}
	headers := map[string]string{"Idempotency-Key": "idem-2", "X-QWQ-Request-ID": "request-2"}
	accepted := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", payload, "provider-token", headers)
	repeated := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", payload, "provider-token", headers)
	if accepted.Code != http.StatusAccepted || repeated.Body.String() != accepted.Body.String() {
		t.Fatalf("idempotency mismatch: %d %q %q", repeated.Code, accepted.Body.String(), repeated.Body.String())
	}
	conflictPayload := providerPayload(now.Add(time.Minute), "request-2", "+8613800000000", "111111")
	conflict := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", conflictPayload, "provider-token", headers)
	if conflict.Code != http.StatusConflict {
		t.Fatalf("idempotency conflict status=%d", conflict.Code)
	}

	for scene, status := range map[string]int{"rate_limit": 429, "failure": 502, "timeout": 504} {
		requestID := "scene-" + scene
		body := providerPayload(now.Add(time.Minute), requestID, "+8613900000000", "123456")
		response := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", body, "provider-token", map[string]string{
			"Idempotency-Key": requestID, "X-QWQ-Request-ID": requestID, "X-QWQ-Debug-Scenario": scene,
		})
		if response.Code != status {
			t.Fatalf("scene=%s status=%d body=%s", scene, response.Code, response.Body.String())
		}
	}

	expired := providerPayload(now.Add(-time.Second), "expired", "+8613700000000", "654321")
	response := perform(t, s.Handler(), http.MethodPost, "/v1/provider/sms/send", expired, "provider-token", map[string]string{
		"Idempotency-Key": "expired", "X-QWQ-Request-ID": "expired",
	})
	if response.Code != http.StatusBadRequest || strings.Contains(response.Body.String(), "654321") {
		t.Fatalf("expired response=%d %s", response.Code, response.Body.String())
	}
}

func TestRequestBodyOverLimitIsRejected(t *testing.T) {
	now := time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC)
	s := newTestServer(t, now)
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/provider/sms/send",
		strings.NewReader(strings.Repeat("x", maxRequestBytes+1)),
	)
	request.Header.Set("Authorization", "Bearer provider-token")
	response := httptest.NewRecorder()
	s.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("oversized request status=%d", response.Code)
	}
}

func newTestServer(t *testing.T, now time.Time) *Server {
	t.Helper()
	s, err := New(Config{
		Environment: "alpha", ConfigurationDigest: "sha256:" + strings.Repeat("a", 64),
		ProviderToken: "provider-token", OperatorToken: "operator-token",
		CaptureKey: bytes.Repeat([]byte{7}, 32), TimeoutDelay: time.Millisecond, Now: func() time.Time { return now },
	})
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func providerPayload(expires time.Time, requestID, recipient, code string) map[string]any {
	return map[string]any{
		"requestId": requestID, "operation": OperationSMSOTP, "env": "alpha",
		"idempotencyKey": strings.Replace(requestID, "request-", "idem-", 1),
		"expiresAt":      expires.Format(time.RFC3339),
		"payload":        map[string]string{"recipient": recipient, "code": code, "templateId": "login_otp"},
	}
}

func perform(t *testing.T, handler http.Handler, method, path string, payload any, token string, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(raw))
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}
