package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/intersectionclient"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type migratedClientAuthorizationStub struct{}

func (migratedClientAuthorizationStub) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	return "Bearer delegated-" + personaID, nil
}

func TestListNewIntersectionReasonsReadsFactSliceWithDelegatedIdentity(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/content/intersections" {
			t.Fatalf("request=%s %s", r.Method, r.URL.Path)
		}
		if r.URL.Query().Get("filter") != "new" || r.URL.Query().Get("limit") != "8" {
			t.Fatalf("query=%s", r.URL.RawQuery)
		}
		if r.Header.Get("Authorization") != "Bearer delegated-persona-1" {
			t.Fatalf("authorization=%q", r.Header.Get("Authorization"))
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
		  "items": [
		    {
		      "intersectionId": "intersection-new",
		      "relationObjectId": "circle-1",
		      "displayName": "川西摄影圈",
		      "dimension": "circle",
		      "primaryText": "你关注的3人加入了川西摄影圈",
		      "intersectionClass": "fact",
		      "freshAt": "2026-07-20T10:00:00Z"
		    },
		    {
		      "intersectionId": "intersection-old",
		      "relationObjectId": "circle-2",
		      "displayName": "旧圈子",
		      "dimension": "circle",
		      "primaryText": "旧交集",
		      "intersectionClass": "fact",
		      "freshAt": "2026-07-18T10:00:00Z"
		    },
		    {
		      "intersectionId": "intersection-affinity",
		      "relationObjectId": "circle-3",
		      "displayName": "推荐圈子",
		      "dimension": "circle",
		      "primaryText": "可能感兴趣",
		      "intersectionClass": "affinity",
		      "freshAt": "2026-07-20T11:00:00Z"
		    }
		  ]
		}`))
	}))
	defer server.Close()
	client, err := New(Config{
		BaseURL:       server.URL,
		HTTPClient:    server.Client(),
		Authorization: migratedClientAuthorizationStub{},
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	reasons, err := client.ListNewIntersectionReasons(
		t.Context(),
		"persona-1",
		time.Date(2026, 7, 19, 0, 0, 0, 0, time.UTC),
		8,
	)
	if err != nil {
		t.Fatalf("list reasons: %v", err)
	}
	if len(reasons) != 2 {
		t.Fatalf("reasons=%+v", reasons)
	}
	if reasons[0].ReasonID != "intersection-new" || !reasons[0].IsFact {
		t.Fatalf("first reason=%+v", reasons[0])
	}
	if reasons[1].ReasonID != "intersection-affinity" || reasons[1].IsFact {
		t.Fatalf("second reason=%+v", reasons[1])
	}
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
		Authorization: migratedClientAuthorizationStub{},
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
	if !errors.Is(err, orchestration.ErrIntersectionEvidenceNotFound) {
		t.Fatalf("stale reference error = %v, want not found", err)
	}
}
