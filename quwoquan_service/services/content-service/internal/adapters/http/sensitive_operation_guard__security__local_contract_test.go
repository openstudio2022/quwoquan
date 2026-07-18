package http

import (
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func verifiedPrincipal(accountID, personaID string) rtauth.Principal {
	return rtauth.Principal{
		Claims: rtauth.Claims{
			Subject: accountID,
			Persona: personaID,
		},
		Actor: operation.ActorContext{
			AccountID: accountID,
			PersonaID: personaID,
		},
	}
}

func TestSensitiveOperationGuardRejectsForgedIdentityWithoutPrincipal(t *testing.T) {
	t.Parallel()

	called := false
	handler := RequireSensitiveOperationPrincipal(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			called = true
			w.WriteHeader(http.StatusNoContent)
		},
	))
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", nil)
	req.Header.Set("X-Client-User-Id", "forged-user")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d, want %d: %s", rec.Code, http.StatusUnauthorized, rec.Body.String())
	}
	if called {
		t.Fatal("sensitive operation reached downstream without verified principal")
	}
}

func TestSensitiveOperationGuardAcceptsVerifiedPrincipalAndKeepsPublicRoute(t *testing.T) {
	t.Parallel()

	handler := RequireSensitiveOperationPrincipal(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		},
	))
	principal := verifiedPrincipal("account-1", "persona-1")
	sensitive := httptest.NewRequest(http.MethodPost, "/content/media/uploads/session-1:complete", nil)
	sensitive = sensitive.WithContext(rtauth.WithPrincipal(sensitive.Context(), principal))
	sensitiveRec := httptest.NewRecorder()
	handler.ServeHTTP(sensitiveRec, sensitive)
	if sensitiveRec.Code != http.StatusNoContent {
		t.Fatalf("verified sensitive status=%d", sensitiveRec.Code)
	}

	public := httptest.NewRequest(http.MethodGet, "/content/feed", nil)
	publicRec := httptest.NewRecorder()
	handler.ServeHTTP(publicRec, public)
	if publicRec.Code != http.StatusNoContent {
		t.Fatalf("public status=%d", publicRec.Code)
	}
}

func TestVerifiedOperationActorUsesPersonaFromTrustedClaims(t *testing.T) {
	t.Parallel()

	req := httptest.NewRequest(http.MethodPost, "/content/behaviors?userId=forged", nil)
	req = req.WithContext(rtauth.WithPrincipal(
		req.Context(),
		verifiedPrincipal("account-1", "persona-1"),
	))
	actorID, ok := verifiedOperationActorID(req)
	if !ok || actorID != "persona-1" {
		t.Fatalf("actor=(%q,%v), want trusted persona", actorID, ok)
	}
}
