package main

import (
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestVerifiedTelemetryActorHashUsesOnlyVerifiedBusinessActor(t *testing.T) {
	t.Parallel()

	request := httptest.NewRequest("POST", "/ops/events", nil)
	request.Header.Set("X-Client-User-Id", "attacker-controlled")
	if _, ok := verifiedTelemetryActorHash(request); ok {
		t.Fatal("unverified request must not yield telemetry actor")
	}

	principal := rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "persona-verified"},
	}
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
	first, ok := verifiedTelemetryActorHash(request)
	if !ok || first == "" {
		t.Fatal("verified persona must yield telemetry actor hash")
	}
	second, ok := verifiedTelemetryActorHash(request)
	if !ok || first != second {
		t.Fatal("verified actor hash must be stable")
	}
}
