package application

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestResolveObjectPageIntersectionsUsesContentService(t *testing.T) {
	t.Setenv("CONTENT_SERVICE_BASE_URL", "")

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Path; got != contentServiceObjectIntersectionsPath {
			t.Fatalf("path=%q want %q", got, contentServiceObjectIntersectionsPath)
		}
		if got := r.Header.Get("X-Client-User-Id"); got != "viewer_1" {
			t.Fatalf("viewer header=%q want viewer_1", got)
		}
		if got := r.URL.Query().Get("objectId"); got != "entity:university:pku" {
			t.Fatalf("objectId=%q want entity:university:pku", got)
		}
		if got := r.URL.Query().Get("objectType"); got != "university" {
			t.Fatalf("objectType=%q want university", got)
		}
		if got := r.URL.Query().Get("limit"); got != "8" {
			t.Fatalf("limit=%q want 8", got)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{
					"intersectionId": "remote_1",
					"dimension":      "identity",
					"source":         "remote",
				},
			},
		})
	}))
	defer server.Close()

	t.Setenv("CONTENT_SERVICE_BASE_URL", server.URL)

	homepage := &Homepage{
		ID:                "homepage_1",
		HomepageType:      "university",
		CanonicalEntityID: "entity:university:pku",
	}

	reasons := resolveObjectPageIntersections(context.Background(), "viewer_1", homepage, nil)
	if len(reasons) != 1 {
		t.Fatalf("reasons len=%d want 1", len(reasons))
	}
	if got := reasons[0]["intersectionId"]; got != "remote_1" {
		t.Fatalf("reasons[0].intersectionId=%v want remote_1", got)
	}
	if got := reasons[0]["source"]; got != "remote" {
		t.Fatalf("reasons[0].source=%v want remote", got)
	}
}
