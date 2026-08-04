// spec_ref: specs/feature-tree/runtime/runtime-external-integration/spec.md#sit-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-003
package local_contract

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

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
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedIdempotency = r.Header.Get("Idempotency-Key")
		if r.Header.Get("Authorization") == "" {
			t.Fatalf("authorization header missing")
		}
		_, _ = io.ReadAll(r.Body)
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
	}); err != nil {
		t.Fatalf("submit: %v", err)
	}
	if capturedIdempotency != "otp:hash:202608041200" {
		t.Fatalf("Idempotency-Key = %q, want otp:hash:202608041200", capturedIdempotency)
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
