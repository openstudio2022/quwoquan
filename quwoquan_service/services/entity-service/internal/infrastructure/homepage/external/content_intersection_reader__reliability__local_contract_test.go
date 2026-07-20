package external

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/entity-service/internal/application"
)

func TestContentIntersectionReaderUsesInjectedPathAndSanitizesInternalEvidence(t *testing.T) {
	var path string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path = r.URL.Path
		if r.Header.Get("Authorization") == "" {
			t.Error("delegated Authorization header is required")
		}
		if r.Header.Get("X-Client-User-Id") != "" {
			t.Error("legacy client identity header must not be forwarded")
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{{
				"intersectionId":     "reason-1",
				"primaryText":        "真实交集理由",
				"sourceRefs":         []string{"internal"},
				"primaryEvidenceRef": "internal",
			}},
		})
	}))
	defer server.Close()
	credentials := testDelegatedCredentials(t)
	reader, err := NewContentIntersectionReader(ContentIntersectionConfig{
		BaseURL: server.URL, ObjectIntersectionsPath: "/configured/intersections",
		Authorization: credentials,
	})
	if err != nil {
		t.Fatalf("new reader: %v", err)
	}
	items, err := reader.ListObjectIntersections(context.Background(), application.ObjectIntersectionQuery{
		ViewerPersonaID: "persona-1", ObjectID: "hp-1",
		CanonicalEntityID: "entity:sight:west_lake", HomepageType: "sight", Limit: 8,
	})
	if err != nil {
		t.Fatalf("list intersections: %v", err)
	}
	if path != "/configured/intersections" || len(items) != 1 {
		t.Fatalf("injected path/items mismatch: path=%q items=%d", path, len(items))
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(items[0], &fields); err != nil {
		t.Fatalf("decode item: %v", err)
	}
	if _, leaked := fields["sourceRefs"]; leaked {
		t.Fatal("sourceRefs leaked")
	}
	if _, leaked := fields["primaryEvidenceRef"]; leaked {
		t.Fatal("primaryEvidenceRef leaked")
	}
}

func TestContentIntersectionReaderFailsStructuredOnDependencyError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "unavailable", http.StatusServiceUnavailable)
	}))
	defer server.Close()
	credentials := testDelegatedCredentials(t)
	reader, err := NewContentIntersectionReader(ContentIntersectionConfig{
		BaseURL: server.URL, ObjectIntersectionsPath: "/configured/intersections",
		Authorization: credentials,
	})
	if err != nil {
		t.Fatalf("new reader: %v", err)
	}
	if _, err := reader.ListObjectIntersections(context.Background(), application.ObjectIntersectionQuery{
		ViewerPersonaID: "persona-1", ObjectID: "hp-1", HomepageType: "homepage",
	}); err == nil {
		t.Fatal("dependency failure must return a structured error")
	}
}

func testDelegatedCredentials(
	t *testing.T,
) rtauth.DelegatedPersonaAuthorizationProvider {
	t.Helper()
	provider, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		rtauth.TokenConfig{
			Secret:       []byte("entity-homepage-test-secret-at-least-32-bytes"),
			Issuer:       "quwoquan-test",
			Audience:     "quwoquan-test",
			Type:         rtauth.TokenTypeAccess,
			TokenVersion: 1,
			TTL:          time.Minute,
			ClockSkew:    time.Second,
		},
		"entity-service",
		[]string{"content.object_intersections.read"},
	)
	if err != nil {
		t.Fatalf("new delegated credentials: %v", err)
	}
	return provider
}
