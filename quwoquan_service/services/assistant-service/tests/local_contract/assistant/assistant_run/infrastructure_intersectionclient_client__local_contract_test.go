package assistant_run_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/intersectionclient"
)

type assistantRunClientAuthorizationStub struct{}

func (assistantRunClientAuthorizationStub) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	return "Bearer delegated-" + personaID, nil
}

func TestResolveAuthorizedIntersectionEvidenceRejectsStaleOrForgedReferences(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/content/intersections/object" {
			t.Fatalf("request=%s %s", r.Method, r.URL.Path)
		}
		if r.URL.Query().Get("objectId") != "post-1" ||
			r.URL.Query().Get("objectType") != "post" {
			t.Fatalf("query=%s", r.URL.RawQuery)
		}
		if r.Header.Get("Authorization") != "Bearer delegated-persona-1" {
			t.Fatalf("authorization=%q", r.Header.Get("Authorization"))
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
		  "items": [{
		    "intersectionId": "intersection-current",
		    "pointSummarySnapshotId": "snapshot-current",
		    "kind": "same_school",
		    "primaryText": "服务端当前可见的共同学校",
		    "dimension": "education"
		  }]
		}`))
	}))
	defer server.Close()
	client, err := New(Config{
		BaseURL:       server.URL,
		HTTPClient:    server.Client(),
		Authorization: assistantRunClientAuthorizationStub{},
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	currentRef := assistant.AssistantIntersectionEvidenceRef{
		IntersectionID: "intersection-current",
		EvidenceID:     "snapshot-current",
		SourceRef:      "same_school",
		ObjectTypeRef:  "post",
		ObjectID:       "post-1",
	}
	resolved, err := client.ResolveAuthorizedIntersectionEvidence(
		t.Context(),
		"persona-1",
		[]assistant.AssistantIntersectionEvidenceRef{currentRef},
	)
	if err != nil {
		t.Fatalf("resolve current evidence: %v", err)
	}
	if len(resolved) != 1 ||
		resolved[0].PrimaryText != "服务端当前可见的共同学校" ||
		resolved[0].EvidenceID != "snapshot-current" {
		t.Fatalf("resolved=%+v", resolved)
	}
	stale := currentRef
	stale.EvidenceID = "snapshot-stale"
	_, err = client.ResolveAuthorizedIntersectionEvidence(
		t.Context(),
		"persona-1",
		[]assistant.AssistantIntersectionEvidenceRef{stale},
	)
	if !errors.Is(err, runapplication.ErrIntersectionEvidenceNotFound) {
		t.Fatalf("stale reference error = %v, want not found", err)
	}
}
