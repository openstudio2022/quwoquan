package api_integration

import (
	"context"
	"net/http"
	"net/url"
	"testing"
)

func TestSocialRelationSearch_SemiPersonaOnlyUsesKnownHandlePath(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createTestProfile(t, "search_viewer_owner", "搜索查看者")
	createTestPersonaFull(
		t,
		"search_viewer_persona",
		"search_viewer_owner",
		"sa_search_viewer",
		"搜索查看者",
		"open",
		true,
	)
	createTestProfile(t, "search_semi_owner", "半公开山友")
	createTestPersonaFull(
		t,
		"search_semi_persona",
		"search_semi_owner",
		"sa_search_semi",
		"半公开山友",
		"semi",
		true,
	)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET user_handle = $1 WHERE persona_id = $2`,
		"known-semi-handle",
		"sa_search_semi",
	); err != nil {
		t.Fatalf("set semi persona handle: %v", err)
	}

	fuzzy := doRequest(
		t,
		http.MethodGet,
		"/user/search/social-relations?query="+url.QueryEscape("半公开山友"),
		"",
		authHeadersForPersona("search_viewer_owner", "sa_search_viewer"),
	)
	if fuzzy.Code != http.StatusOK {
		t.Fatalf("fuzzy search: expected 200, got %d: %s", fuzzy.Code, fuzzy.Body.String())
	}
	assertSearchItemsExcludePersona(t, parseJSON(t, fuzzy), "sa_search_semi")

	knownPath := doRequest(
		t,
		http.MethodGet,
		"/user/search/social-relations?query="+url.QueryEscape("known-semi-handle"),
		"",
		authHeadersForPersona("search_viewer_owner", "sa_search_viewer"),
	)
	if knownPath.Code != http.StatusOK {
		t.Fatalf("known handle search: expected 200, got %d: %s", knownPath.Code, knownPath.Body.String())
	}
	assertSearchItemsContainPersona(t, parseJSON(t, knownPath), "sa_search_semi")
}

func assertSearchItemsExcludePersona(
	t *testing.T,
	body map[string]any,
	personaID string,
) {
	t.Helper()
	for _, raw := range body["items"].([]any) {
		item := raw.(map[string]any)
		if item["personaId"] == personaID {
			t.Fatalf("expected %q to be excluded from fuzzy discovery", personaID)
		}
	}
}

func assertSearchItemsContainPersona(
	t *testing.T,
	body map[string]any,
	personaID string,
) {
	t.Helper()
	for _, raw := range body["items"].([]any) {
		item := raw.(map[string]any)
		if item["personaId"] == personaID {
			return
		}
	}
	t.Fatalf("expected known-path result for %q, got %#v", personaID, body)
}
