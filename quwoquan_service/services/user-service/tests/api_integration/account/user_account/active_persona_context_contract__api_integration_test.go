// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// readiness_case: get-active-persona-context-api
package api_integration

import (
	"net/http"
	"testing"
)

func TestActivePersonaContext_CarriesAvatarVersionedUrl(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_active_context", "owner_active_context")
	createTestPersonaFull(t, "persona_active_context", "owner_active_context", "sa_active_context", "当前分身", "open", true, true)
	seedPersonaAvatarVersion(
		t,
		"sa_active_context",
		"https://cdn.example.com/active-context-avatar.png",
		11,
	)

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/personas/active",
		"",
		authHeaders("owner_active_context"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("get active persona context: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	if body["personaId"] != "sa_active_context" {
		t.Fatalf("expected active personaId, got %#v", body["personaId"])
	}
	if body["avatarUrl"] != "https://cdn.example.com/active-context-avatar.png?v=11" {
		t.Fatalf("expected versioned avatarUrl, got %#v", body["avatarUrl"])
	}
	if body["avatarVersion"] != float64(11) {
		t.Fatalf("expected avatarVersion=11, got %#v", body["avatarVersion"])
	}
}
