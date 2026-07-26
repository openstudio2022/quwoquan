package http_test

import (
	"net/http/httptest"
	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
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

	if got := ResolveUserID(request); got != "trusted-account" {
		t.Fatalf("user id=%q, want trusted account", got)
	}
	if got := ResolvePersonaID(request); got != "trusted-persona" {
		t.Fatalf("persona id=%q, want trusted persona", got)
	}
	if got := ResolveRecommendationActorID(request); got != "trusted-persona" {
		t.Fatalf("recommendation actor=%q, want trusted persona", got)
	}
	if got := ResolveDeviceActorID(request); got != "trusted-device" {
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

	if got := ResolvePersonaID(request); got != "persona-intersection-viewer" {
		t.Fatalf("intersection actor=%q, want verified persona", got)
	}
}

func TestBlockedKeywordHeaderDecodesEachOpaqueValue(t *testing.T) {
	t.Parallel()

	request := httptest.NewRequest("GET", "/content/feed", nil)
	request.Header.Set(
		"X-Blocked-Keywords",
		"%E9%87%8D%E5%A4%8D%2C%E8%90%A5%E9%94%80,%E5%89%A7%E9%80%8F",
	)

	got := ResolveBlockedKeywords(request)
	if len(got) != 2 || got[0] != "重复,营销" || got[1] != "剧透" {
		t.Fatalf("decoded blocked keywords=%v", got)
	}
}
