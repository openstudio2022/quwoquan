// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-005
package assistant_run_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/searchclient"
)

type searchAuthorizationFixture struct{}

func (searchAuthorizationFixture) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer signed-assistant-search", nil
}

func TestAppSearchExecutesFrozenPlanAsOrderedCanonicalOwnerQueries(t *testing.T) {
	var calls atomic.Int32
	var mutex sync.Mutex
	received := make([]map[string]any, 0, 2)
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		calls.Add(1)
		if request.Header.Get("Authorization") != "Bearer signed-assistant-search" ||
			request.Header.Get("X-Contract-Graph-SHA256") != testSHA256 {
			t.Errorf("owner identity headers=%v", request.Header)
		}
		var body map[string]any
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Errorf("decode owner request: %v", err)
			writer.WriteHeader(http.StatusBadRequest)
			return
		}
		mutex.Lock()
		received = append(received, body)
		mutex.Unlock()
		query, _ := body["query"].(string)
		writer.Header().Set("Content-Type", "application/json")
		writer.Header().Set("X-Contract-Graph-SHA256", testSHA256)
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"interpretedQuery": map[string]any{
				"normalized": query, "tokens": []string{}, "variants": []string{},
				"detectedEntities": []string{}, "detectedTags": []string{}, "selectedObjectTypes": []string{"content.post"},
			},
			"hits": []map[string]any{{
				"objectRef": "opaque:" + query, "objectType": "content.post", "contentType": "article",
				"title": query + "结果", "snippet": "公开摘要",
			}},
			"citations": []map[string]any{{
				"citationId": "citation:" + query, "objectRef": "opaque:" + query,
				"objectType": "content.post", "contentType": "article", "title": query + "结果",
				"snippet": "公开摘要", "url": "", "deepLink": "",
			}},
			"facets": []any{}, "degradeSignals": []any{},
			"provenance": map[string]any{"source": "search_index_view", "generatedAt": time.Unix(1_700_000_000, 0).UTC()},
			"nextCursor": "",
		})
	}))
	defer server.Close()

	client, err := searchclient.New(server.URL, server.Client(), searchAuthorizationFixture{}, testSHA256)
	if err != nil {
		t.Fatalf("new owner search client: %v", err)
	}
	result, err := client.Handler()(t.Context(), toolpkg.Request{
		ToolName: "app_search", RunID: "run-search-1", TurnID: "turn-search-1",
		ToolCatalogDigest: testSHA256, RuntimeCandidateDigest: testSHA256,
		ContractGraphDigest: testSHA256, MaximumToolCalls: 4,
		Input: map[string]any{
			"goal": "规划杭州亲子露营", "query": "杭州亲子露营",
			"searchQueries": []any{map[string]any{
				"dimension": "place", "query": "杭州亲子露营地点",
				"objectTypes": []any{"content.post"}, "limit": float64(8),
			}},
			"evidenceCriteria": []any{"至少一个可引用结果"}, "maximumQueries": float64(2),
		},
	})
	if err != nil {
		t.Fatalf("execute app_search: %v", err)
	}
	if calls.Load() != 2 {
		t.Fatalf("owner calls=%d want 2", calls.Load())
	}
	buckets, ok := result.Output["resultBuckets"].([]any)
	if !ok || len(buckets) != 2 {
		t.Fatalf("ordered buckets=%#v", result.Output["resultBuckets"])
	}
	first := buckets[0].(map[string]any)
	second := buckets[1].(map[string]any)
	if first["dimension"] != "primary" || second["dimension"] != "place" {
		t.Fatalf("bucket order drifted: %#v", buckets)
	}
	encoded, _ := json.Marshal(result.Output)
	for _, forbidden := range []string{"objectId", "score", "provider", "search_after"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("tool output leaked %q: %s", forbidden, encoded)
		}
	}
	plan, ok := result.Output["retrievalPlan"].(map[string]any)
	if !ok || !strings.HasPrefix(plan["digest"].(string), "sha256:") {
		t.Fatalf("retrieval plan=%#v", result.Output["retrievalPlan"])
	}
}

func TestAppSearchRejectsUnboundOrOverBudgetPlanBeforeOwnerCall(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { calls.Add(1) }))
	defer server.Close()
	client, err := searchclient.New(server.URL, server.Client(), searchAuthorizationFixture{}, testSHA256)
	if err != nil {
		t.Fatalf("new owner search client: %v", err)
	}
	_, err = client.Handler()(t.Context(), toolpkg.Request{
		ToolName: "app_search", RunID: "run-search-2", TurnID: "turn-search-2",
		ToolCatalogDigest: testSHA256, ContractGraphDigest: testSHA256, MaximumToolCalls: 1,
		Input: map[string]any{
			"query": "杭州", "searchQueries": []any{map[string]any{"dimension": "place", "query": "杭州地点"}},
		},
	})
	if err == nil {
		t.Fatal("unbound and over-budget retrieval plan was accepted")
	}
	if calls.Load() != 0 {
		t.Fatalf("rejected plan reached owner %d time(s)", calls.Load())
	}
}
