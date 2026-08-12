// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package assistant_run_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/searchclient"
)

func TestAppSearchRejectsOwnerHitsThatObjectContractsClose(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		writer.Header().Set("X-Contract-Graph-SHA256", testSHA256)
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"interpretedQuery": map[string]any{
				"normalized": "西湖", "tokens": []string{}, "variants": []string{},
				"detectedEntities": []string{}, "detectedTags": []string{}, "selectedObjectTypes": []string{},
			},
			"hits": []map[string]any{{
				"objectRef": "opaque-private", "objectType": "chat.message", "title": "私密消息",
			}},
			"citations": []any{}, "facets": []any{}, "degradeSignals": []any{},
			"provenance": map[string]any{"source": "search_index_view", "generatedAt": time.Unix(1_700_000_000, 0).UTC()},
			"nextCursor": "",
		})
	}))
	defer server.Close()
	client, err := searchclient.New(server.URL, server.Client(), searchAuthorizationFixture{}, testSHA256)
	if err != nil {
		t.Fatalf("new search client: %v", err)
	}
	_, err = client.Handler()(t.Context(), boundSearchRequest(map[string]any{"query": "西湖"}, 1))
	if err == nil {
		t.Fatal("owner widened result escaped Assistant access enforcement")
	}
}

func TestAppSearchClosedObjectTypeFailsBeforeOwnerCall(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { calls.Add(1) }))
	defer server.Close()
	client, err := searchclient.New(server.URL, server.Client(), searchAuthorizationFixture{}, testSHA256)
	if err != nil {
		t.Fatalf("new search client: %v", err)
	}
	_, err = client.Handler()(t.Context(), boundSearchRequest(map[string]any{
		"query": "西湖",
		"searchQueries": []any{map[string]any{
			"dimension": "private", "query": "聊天", "objectTypes": []any{"chat.message"},
		}},
	}, 2))
	if err == nil {
		t.Fatal("closed object type was accepted")
	}
	if calls.Load() != 0 {
		t.Fatalf("closed object request reached owner %d time(s)", calls.Load())
	}
}

func TestAssistantSearchAccessIsGeneratedAndDigestBound(t *testing.T) {
	readable := searchclient.AssistantReadableObjectTypes()
	if len(readable) == 0 || searchclient.AssistantAccessPolicyDigest() == "" {
		t.Fatalf("generated assistant access is empty: readable=%v digest=%q", readable, searchclient.AssistantAccessPolicyDigest())
	}
	readable[0] = "mutated"
	if searchclient.AssistantReadableObjectTypes()[0] == "mutated" {
		t.Fatal("callers can mutate generated assistant access")
	}
}

func boundSearchRequest(input map[string]any, maximumToolCalls int) toolpkg.Request {
	return toolpkg.Request{
		ToolName: "app_search", RunID: "run-access", TurnID: "turn-access",
		ToolCatalogDigest: testSHA256, RuntimeCandidateDigest: testSHA256,
		ContractGraphDigest: testSHA256, MaximumToolCalls: maximumToolCalls,
		Input: input,
	}
}
