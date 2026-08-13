// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001.t4
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/greeting-intersection-context/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/greeting-intersection-context/spec.md#gwt-002
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	greetingmodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
	greetingintegration "quwoquan_service/services/user-service/internal/relationship/greeting_request/infrastructure/integration"
)

type greetingTestAuthorization struct{}

func (greetingTestAuthorization) AuthorizationHeaderForPersona(
	context.Context,
	string,
) (string, error) {
	return "Bearer delegated", nil
}

func TestGreetingIntersectionResolverFreezesServerText(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/content/intersections/object" ||
			r.URL.Query().Get("objectType") != "user" ||
			r.URL.Query().Get("objectId") != "persona-b" ||
			r.Header.Get("Authorization") != "Bearer delegated" {
			http.Error(w, "unexpected request", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{
					"intersectionId":         "intersection-1",
					"pointSummarySnapshotId": "evidence-1",
					"kind":                   "coVisitedEntity",
					"primaryText":            "服务端解析：你们都去过老君山",
					"dimension":              "destination",
				},
			},
		})
	}))
	t.Cleanup(server.Close)
	resolver, err := greetingintegration.NewIntersectionResolver(
		server.URL,
		server.Client(),
		greetingTestAuthorization{},
	)
	if err != nil {
		t.Fatalf("new greeting intersection resolver: %v", err)
	}
	ref := greetingmodel.GreetingIntersectionRef{
		IntersectionID: "intersection-1",
		EvidenceID:     "evidence-1",
		SourceRef:      "coVisitedEntity",
		ObjectTypeRef:  "user",
		ObjectID:       "persona-b",
	}
	snapshot, err := resolver.ResolveGreetingIntersection(
		context.Background(),
		"persona-a",
		"persona-b",
		ref,
	)
	if err != nil {
		t.Fatalf("resolve greeting intersection: %v", err)
	}
	if snapshot == nil || snapshot.PrimaryText != "服务端解析：你们都去过老君山" ||
		snapshot.ObjectID != "persona-b" || snapshot.ResolvedAt.IsZero() {
		t.Fatalf("unexpected frozen snapshot: %+v", snapshot)
	}
}

func TestGreetingIntersectionResolverRejectsStaleEvidence(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"items":[]}`))
	}))
	t.Cleanup(server.Close)
	resolver, err := greetingintegration.NewIntersectionResolver(
		server.URL,
		server.Client(),
		greetingTestAuthorization{},
	)
	if err != nil {
		t.Fatalf("new greeting intersection resolver: %v", err)
	}
	_, err = resolver.ResolveGreetingIntersection(
		context.Background(),
		"persona-a",
		"persona-b",
		greetingmodel.GreetingIntersectionRef{
			IntersectionID: "intersection-stale",
			EvidenceID:     "evidence-stale",
			SourceRef:      "coVisitedEntity",
			ObjectTypeRef:  "user",
			ObjectID:       "persona-b",
		},
	)
	if err == nil {
		t.Fatal("stale intersection evidence must not become a greeting snapshot")
	}
}
