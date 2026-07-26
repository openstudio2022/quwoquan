package local_contract

import (
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestMessageActorUsesVerifiedPersonaWithoutOwnerFallback(t *testing.T) {
	t.Parallel()

	request := httptest.NewRequest("POST", "/chat/conversations/c1/messages", nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "owner-verified", PersonaID: "persona-verified"},
	}))
	principal, found := rtauth.PrincipalFromContext(request.Context())
	if !found {
		t.Fatal("verified principal must be available to the inbound command boundary")
	}
	if principal.Actor.AccountID != "owner-verified" || principal.Actor.PersonaID != "persona-verified" {
		t.Fatalf("verified actor drift: %+v", principal.Actor)
	}
}
