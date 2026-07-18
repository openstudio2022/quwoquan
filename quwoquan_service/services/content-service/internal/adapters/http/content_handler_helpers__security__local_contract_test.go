package http

import (
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestTrustedPrincipalOverridesClientActorSelectors(t *testing.T) {
	t.Parallel()

	request := httptest.NewRequest(
		"GET",
		"/content/feed?userId=forged-account&deviceActorId=forged-device",
		nil,
	)
	request.Header.Set("X-Client-User-Id", "forged-account-header")
	request.Header.Set("X-Client-Device-Actor-Id", "forged-device-header")
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID:     "trusted-account",
				PersonaID:     "trusted-persona",
				DeviceActorID: "trusted-device",
			},
		},
	))

	if got := resolveUserID(request); got != "trusted-account" {
		t.Fatalf("user id=%q, want trusted account", got)
	}
	if got := resolvePersonaID(request); got != "trusted-persona" {
		t.Fatalf("persona id=%q, want trusted persona", got)
	}
	if got := resolveDeviceActorID(request); got != "trusted-device" {
		t.Fatalf("device actor id=%q, want trusted device", got)
	}
}

func TestIntersectionActorUsesVerifiedPersonaRatherThanOwnerAccount(t *testing.T) {
	t.Parallel()

	request := httptest.NewRequest("GET", "/content/intersections/object", nil)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "owner-account-must-not-enter-intersection-store",
			PersonaID: "persona-intersection-viewer",
		}},
	))

	if got := resolvePersonaID(request); got != "persona-intersection-viewer" {
		t.Fatalf("intersection actor=%q, want verified persona", got)
	}
}
