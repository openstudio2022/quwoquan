package tests

import (
	"context"
	"net/http"
	"testing"
)

func TestActivePersonaContext_CarriesAvatarVersionedUrl(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_active_context", "owner_active_context")
	createTestPersonaFull(t, "persona_active_context", "owner_active_context", "sa_active_context", "当前分身", "open", true, true)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles SET avatar_url = $1, avatar_version = $2 WHERE user_id = $3`,
		"https://cdn.example.com/active-context-avatar.png",
		11,
		"owner_active_context",
	); err != nil {
		t.Fatalf("seed active context avatar version: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/personas/active",
		"",
		authHeaders("owner_active_context"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("get active persona context: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	if body["subAccountId"] != "sa_active_context" {
		t.Fatalf("expected active subAccountId, got %#v", body["subAccountId"])
	}
	if body["avatarUrl"] != "https://cdn.example.com/active-context-avatar.png?v=11" {
		t.Fatalf("expected versioned avatarUrl, got %#v", body["avatarUrl"])
	}
	if body["avatarVersion"] != float64(11) {
		t.Fatalf("expected avatarVersion=11, got %#v", body["avatarVersion"])
	}
}
