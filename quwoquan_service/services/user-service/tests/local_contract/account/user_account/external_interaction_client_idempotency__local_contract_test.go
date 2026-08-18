// spec_ref: specs/feature-tree/runtime/runtime-external-integration/spec.md#sit-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-003
package local_contract

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func TestSMSOTPReadinessUsesCapabilityScopedServicePrincipal(t *testing.T) {
	signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "quwoquan.test.local",
		Audience:     "quwoquan-app",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	})
	if err != nil {
		t.Fatalf("signer: %v", err)
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet ||
			r.URL.Path != "/internal/integrations/external-requests/capabilities/identity.sms.otp/readiness" {
			t.Fatalf("unexpected readiness request %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Authorization") == "" {
			t.Fatal("authorization header missing")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"availability":"temporarily_unavailable","retryAfterSeconds":5}`))
	}))
	t.Cleanup(server.Close)

	client, err := userintegration.NewExternalInteractionClient(
		"http://integration-service:18086",
		"gamma",
		&http.Client{Transport: rewriteHostTransport{base: server.URL, next: http.DefaultTransport}},
		signer,
	)
	if err != nil {
		t.Fatalf("client: %v", err)
	}
	readiness, err := client.GetSMSOTPDeliveryReadiness(context.Background())
	if err != nil || readiness.Availability != "temporarily_unavailable" ||
		readiness.RetryAfterSeconds != 5 {
		t.Fatalf("readiness=%+v err=%v", readiness, err)
	}
}

func TestSubmitSMSOTPSetsRequiredIdempotencyKeyHeader(t *testing.T) {
	signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "quwoquan.test.local",
		Audience:     "quwoquan-app",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	})
	if err != nil {
		t.Fatalf("signer: %v", err)
	}

	var capturedIdempotency string
	var captured struct {
		Payload map[string]string `json:"payload"`
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedIdempotency = r.Header.Get("Idempotency-Key")
		if r.Header.Get("Authorization") == "" {
			t.Fatalf("authorization header missing")
		}
		raw, _ := io.ReadAll(r.Body)
		if err := json.Unmarshal(raw, &captured); err != nil {
			t.Fatalf("decode external interaction request: %v", err)
		}
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"requestId":"otp_req_test","status":"accepted","acceptedAt":"2026-08-04T00:00:00Z"}`))
	}))
	t.Cleanup(server.Close)

	client, err := userintegration.NewExternalInteractionClient(
		"http://integration-service:18086",
		"gamma",
		&http.Client{Transport: rewriteHostTransport{base: server.URL, next: http.DefaultTransport}},
		signer,
	)
	if err != nil {
		t.Fatalf("client: %v", err)
	}
	if _, err := client.SubmitSMSOTP(context.Background(), application.SMSOTPDispatchRequest{
		RequestID:      "otp_req_test",
		ChallengeID:    "otp_ch_test",
		PhoneHash:      "hash",
		MaskedPhone:    "+86****0001",
		CodeRef:        "sealed",
		IdempotencyKey: "otp:hash:202608041200",
		ExpiresAt:      time.Now().UTC().Add(5 * time.Minute),
		Platform:       "android",
		RequestRef:     "otp_req_test",
	}); err != nil {
		t.Fatalf("submit: %v", err)
	}
	if capturedIdempotency != "otp:hash:202608041200" {
		t.Fatalf("Idempotency-Key = %q, want otp:hash:202608041200", capturedIdempotency)
	}
	if captured.Payload["platform"] != "android" ||
		captured.Payload["requestRef"] != "otp_req_test" ||
		captured.Payload["templateId"] != "sms_otp_login_android_retriever" {
		t.Fatalf("unexpected typed SMS template payload: %#v", captured.Payload)
	}
}

type rewriteHostTransport struct {
	base string
	next http.RoundTripper
}

func (t rewriteHostTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	cloned := req.Clone(req.Context())
	target, err := http.NewRequestWithContext(req.Context(), req.Method, t.base+req.URL.Path, req.Body)
	if err != nil {
		return nil, err
	}
	target.Header = cloned.Header
	return t.next.RoundTrip(target)
}
