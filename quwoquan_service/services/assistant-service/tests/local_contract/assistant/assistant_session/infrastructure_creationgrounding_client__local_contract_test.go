package local_contract

import (
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/creationgrounding"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/searchclient"
)

func TestCreationGroundingUsesCanonicalSearchAndEntityQueries(t *testing.T) {
	searchServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/search" {
			t.Fatalf("search request=%s %s", r.Method, r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
		  "hits": [{
		    "target": "article",
		    "objectId": "post-1",
		    "title": "峨眉山徒步",
		    "snippet": "旅行路线",
		    "score": 0.9,
		    "matchedTags": ["Topic/旅行", "Topic/摄影"]
		  }],
		  "citations": [],
		  "provenance": {
		    "provider": "native",
		    "generatedAt": "2026-07-20T10:00:00Z"
		  }
		}`))
	}))
	defer searchServer.Close()
	entityServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/homepages/homepage_sight_emeishan" {
			t.Fatalf("entity request=%s %s", r.Method, r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
		  "homepageId": "homepage_sight_emeishan",
		  "title": "峨眉山",
		  "homepageType": "sight",
		  "canonicalEntityId": "entity_emeishan",
		  "status": "published"
		}`))
	}))
	defer entityServer.Close()

	search, err := searchclient.New(searchServer.URL, &http.Client{Timeout: time.Second})
	if err != nil {
		t.Fatalf("new search client: %v", err)
	}
	client, err := New(search, entityServer.URL, &http.Client{Timeout: time.Second})
	if err != nil {
		t.Fatalf("new creation grounding: %v", err)
	}
	tags, err := client.ResolveTagRefs(t.Context(), []string{"峨眉山旅行路线和摄影点"})
	if err != nil {
		t.Fatalf("resolve tags: %v", err)
	}
	if len(tags) != 2 || tags[0] != "Topic/旅行" || tags[1] != "Topic/摄影" {
		t.Fatalf("tags=%v", tags)
	}
	homepages, err := client.ResolveHomepages(t.Context(), []string{"homepage_sight_emeishan"})
	if err != nil {
		t.Fatalf("resolve homepages: %v", err)
	}
	if len(homepages) != 1 ||
		homepages[0].DisplayName != "峨眉山" ||
		homepages[0].CanonicalEntityID != "entity_emeishan" {
		t.Fatalf("homepages=%+v", homepages)
	}
}
