// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/contact-home-intersection-facts/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
)

type contactIntersectionAuthorization struct{}

func (contactIntersectionAuthorization) AuthorizationHeaderForPersona(
	context.Context,
	string,
) (string, error) {
	return "Bearer contact-viewer", nil
}

func TestContactIntersectionResolverReturnsAtMostTwoTypedSummaries(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/content/intersections/object" ||
			r.URL.Query().Get("objectType") != "user" ||
			r.URL.Query().Get("objectId") != "contact-b" ||
			r.URL.Query().Get("limit") != "2" ||
			r.Header.Get("Authorization") != "Bearer contact-viewer" {
			http.Error(w, "unexpected request", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{"intersectionId": "i-1", "pointSummarySnapshotId": "e-1", "kind": "coVisitedEntity", "primaryText": "都去过老君山", "dimension": "destination"},
				{"intersectionId": "i-2", "pointSummarySnapshotId": "e-2", "kind": "sharedTag", "primaryText": "都喜欢旅行摄影", "dimension": "interest"},
				{"intersectionId": "i-3", "pointSummarySnapshotId": "e-3", "kind": "sharedCircle", "primaryText": "不应进入第三条", "dimension": "community"},
			},
		})
	}))
	t.Cleanup(server.Close)
	resolver, err := httpadapter.NewContactIntersectionResolverClient(
		server.URL,
		server.Client(),
		contactIntersectionAuthorization{},
	)
	if err != nil {
		t.Fatalf("new contact intersection resolver: %v", err)
	}
	items, err := resolver.ListContactIntersections(
		context.Background(),
		"viewer-a",
		"contact-b",
		99,
	)
	if err != nil {
		t.Fatalf("list contact intersections: %v", err)
	}
	if len(items) != 2 || items[0].ObjectTypeRef != "user" ||
		items[0].ObjectID != "contact-b" || items[1].PrimaryText != "都喜欢旅行摄影" {
		t.Fatalf("unexpected typed summaries: %+v", items)
	}
}
