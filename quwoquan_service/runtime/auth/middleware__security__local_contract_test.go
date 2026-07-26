package auth

// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-002

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestMiddlewareClearsForgedIdentityWithoutVerifiedToken(t *testing.T) {
	t.Parallel()

	handler := Middleware(MiddlewareConfig{
		AccessTokenVerifier: mustVerifier(t, testTokenConfig(TokenTypeAccess)),
	})(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			for _, header := range []string{
				clientUserIDHeader,
				clientSubAccountIDHdr,
				clientAccountIDHeader,
				clientPersonaIDHeader,
				clientDeviceActorHdr,
				untrustedUserIDHeader,
				untrustedActorHeader,
			} {
				if got := r.Header.Get(header); got != "" {
					t.Errorf("%s=%q, want cleared", header, got)
				}
			}
			if _, ok := PrincipalFromContext(r.Context()); ok {
				t.Error("unverified request must not contain principal")
			}
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set(clientUserIDHeader, "forged-user")
	req.Header.Set(clientSubAccountIDHdr, "forged-sub-account")
	req.Header.Set(clientAccountIDHeader, "forged-account")
	req.Header.Set(clientPersonaIDHeader, "forged-persona")
	req.Header.Set(clientDeviceActorHdr, "forged-device")
	req.Header.Set(untrustedUserIDHeader, "forged-untrusted-user")
	req.Header.Set(untrustedActorHeader, "forged-untrusted-actor")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestMiddlewareRebuildsIdentityFromVerifiedClaims(t *testing.T) {
	t.Parallel()

	config := testTokenConfig(TokenTypeAccess)
	token, err := mustSigner(t, config).Sign(TokenSubject{
		AccountID: "account-1",
		PersonaID: "persona-1",
		Scopes:    []string{"app"},
	})
	if err != nil {
		t.Fatal(err)
	}
	handler := Middleware(MiddlewareConfig{
		AccessTokenVerifier: mustVerifier(t, config),
	})(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if got := r.Header.Get(clientAccountIDHeader); got != "account-1" {
				t.Errorf("account header=%q", got)
			}
			if got := r.Header.Get(clientPersonaIDHeader); got != "persona-1" {
				t.Errorf("persona header=%q", got)
			}
			if got := r.Header.Get(clientDeviceActorHdr); got != "" {
				t.Errorf("device header=%q, want cleared until device ticket verification", got)
			}
			principal, ok := PrincipalFromContext(r.Context())
			if !ok || principal.Subject != "account-1" || principal.Persona != "persona-1" {
				t.Errorf("principal=%+v ok=%v", principal, ok)
			}
			w.WriteHeader(http.StatusNoContent)
		},
	))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set(clientAccountIDHeader, "forged-account")
	req.Header.Set(clientPersonaIDHeader, "forged-persona")
	req.Header.Set(clientDeviceActorHdr, "forged-device")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("status=%d", rec.Code)
	}
}
