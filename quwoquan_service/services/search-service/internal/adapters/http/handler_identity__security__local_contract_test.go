package http

import (
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestViewerFromUsesVerifiedPersonaAndIgnoresRawUserHeader(t *testing.T) {
	request := httptest.NewRequest("POST", "/search", nil)
	request.Header.Set("X-User-Id", "spoofed-user")
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-1",
			PersonaID: "persona-1",
		}},
	))

	viewer := viewerFrom(request)
	if viewer.UserID != "persona-1" {
		t.Fatalf("viewer=%q, want verified persona", viewer.UserID)
	}
}

func TestViewerFromAnonymousRequestDoesNotTrustHeaders(t *testing.T) {
	request := httptest.NewRequest("POST", "/search", nil)
	request.Header.Set("X-User-Id", "spoofed-user")
	request.Header.Set("X-Client-User-Id", "spoofed-client-user")

	viewer := viewerFrom(request)
	if viewer.UserID != "" {
		t.Fatalf("viewer=%q, want anonymous", viewer.UserID)
	}
}
