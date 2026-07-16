package http

import (
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestMessageActorUsesVerifiedPersonaWithoutOwnerFallback(t *testing.T) {
	t.Parallel()

	request := httptest.NewRequest("POST", "/v1/chat/conversations/c1/messages", nil)
	request.Header.Set("X-Client-User-Id", "owner-1")
	if got := resolvePersonaID(request); got != "" {
		t.Fatalf("persona actor fell back to owner ID: %q", got)
	}

	request.Header.Set("X-Client-Sub-Account-Id", " persona-1 ")
	if got := resolvePersonaID(request); got != "persona-1" {
		t.Fatalf("persona actor = %q, want persona-1", got)
	}

	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "owner-verified", PersonaID: "persona-verified"},
	}))
	if got := resolveUserID(request); got != "owner-verified" {
		t.Fatalf("account actor = %q, want verified account", got)
	}
	if got := resolvePersonaID(request); got != "persona-verified" {
		t.Fatalf("persona actor = %q, want verified persona", got)
	}
}
