package searchclient

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	toolpkg "quwoquan_service/services/assistant-service/internal/application/tool"
)

func TestAppSearchUsesCanonicalSearchQueryAndPreservesCitations(t *testing.T) {
	var received searchRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/search" {
			t.Fatalf("request=%s %s, want POST /search", r.Method, r.URL.Path)
		}
		if err := json.NewDecoder(r.Body).Decode(&received); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
		  "hits": [{
		    "target": "entity",
		    "objectId": "homepage-1",
		    "title": "四川大学",
		    "snippet": "校园主页",
		    "score": 0.98,
		    "rankPosition": 1
		  }],
		  "citations": [{
		    "citationId": "citation-1",
		    "objectType": "entity.homepage",
		    "objectId": "homepage-1",
		    "title": "四川大学",
		    "deepLink": "quwoquan://entity/homepage-1",
		    "score": 0.98
		  }],
		  "provenance": {
		    "provider": "native",
		    "indexVersion": "search-v1",
		    "generatedAt": "2026-07-20T10:00:00Z"
		  }
		}`))
	}))
	defer server.Close()

	client, err := New(server.URL, &http.Client{Timeout: time.Second})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	result, err := client.Handler()(t.Context(), toolpkg.Request{
		ToolName: "app_search",
		Input: map[string]any{
			"query":   "四川大学",
			"targets": []any{"entity"},
			"limit":   float64(8),
		},
	})
	if err != nil {
		t.Fatalf("execute app_search: %v", err)
	}
	if received.Query != "四川大学" || received.Mode != "result" || received.Limit != 8 {
		t.Fatalf("unexpected canonical request: %+v", received)
	}
	citations, ok := result.Output["citations"].([]map[string]any)
	if !ok || len(citations) != 1 {
		t.Fatalf("citations=%T %+v", result.Output["citations"], result.Output["citations"])
	}
	if citations[0]["deepLink"] != "quwoquan://entity/homepage-1" {
		t.Fatalf("deepLink=%v", citations[0]["deepLink"])
	}
}
