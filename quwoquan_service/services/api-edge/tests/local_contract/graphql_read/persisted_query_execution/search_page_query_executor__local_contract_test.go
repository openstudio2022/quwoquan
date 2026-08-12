// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/multi-domain-result-composition/spec.md#gwt-002
// readiness_case: execute-search-page-persisted-graphql-local
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	ownerinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
)

func TestSearchPageExecutorCallsOneResultOwnerAndProjectsOnlyTypedPageFields(t *testing.T) {
	calls := 0
	ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		calls++
		if request.Method != http.MethodPost || request.URL.EscapedPath() != "/search" {
			t.Fatalf("owner request=%s %s", request.Method, request.URL.EscapedPath())
		}
		if request.Header.Get("Authorization") != "Bearer search-owner-token" ||
			request.Header.Get("X-Contract-Graph-SHA256") != "sha256:test-graph" ||
			request.Header.Get("X-Session-Id") != "anon-session-1" {
			t.Fatalf("owner headers=%v", request.Header)
		}
		var payload map[string]any
		decoder := json.NewDecoder(request.Body)
		if err := decoder.Decode(&payload); err != nil {
			t.Fatal(err)
		}
		if payload["mode"] != "result" || payload["query"] != "大理" || payload["limit"] != float64(20) {
			t.Fatalf("owner payload=%v", payload)
		}
		if _, exists := payload["queryText"]; exists {
			t.Fatalf("query text leaked to owner payload=%v", payload)
		}
		writeSearchOwnerResponse(response, map[string]any{
			"interpretedQuery": map[string]any{
				"normalized": "大理", "tokens": []any{"大理"}, "variants": []any{"洱海"},
				"detectedEntities": []any{}, "detectedTags": []any{}, "selectedObjectTypes": []any{"content.post"},
			},
			"hits": []any{map[string]any{
				"objectRef": "objref_v1_opaque_post_1", "objectType": "content.post",
				"contentType": "article", "title": "大理古城", "snippet": "日落路线",
				"thumbnailUrl": "https://cdn.example/post-1.webp",
				"action":       "quwoquan://content/posts/post-1",
			}},
			"citations":      []any{},
			"facets":         []any{map[string]any{"key": "content.post", "label": "内容", "count": 1}},
			"degradeSignals": []any{},
			"provenance":     map[string]any{"source": "search_index_view", "generatedAt": "2026-08-11T00:00:00Z"},
			"nextCursor":     "cursor_v1_opaque_next",
		})
	}))
	defer ownerServer.Close()

	executor := newSearchPageExecutor(t, ownerServer.URL, nil)
	ctx := ownerinfra.WithSearchSessionID(context.Background(), "anon-session-1")
	result, err := executor.Execute(ctx, searchPageEntry(), map[string]any{
		"input": map[string]any{
			"query": "大理", "first": json.Number("20"),
			"objectTypes": []any{"CONTENT_POST"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if calls != 1 || result.Usage.OwnerCalls != 1 || result.Usage.BatchKeys != 1 {
		t.Fatalf("calls=%d usage=%+v", calls, result.Usage)
	}
	encoded := string(result.Data)
	for _, expected := range []string{
		`"searchPage"`, `"items"`, `"objectRef":"objref_v1_opaque_post_1"`,
		`"resultType":"CONTENT_POST"`, `"title":"大理古城"`, `"subtitle":null`,
		`"snippet":"日落路线"`, `"thumbnailUrl":"https://cdn.example/post-1.webp"`,
		`"action":"quwoquan://content/posts/post-1"`, `"facets"`, `"suggestions":["洱海"]`,
		`"nextCursor":"cursor_v1_opaque_next"`,
	} {
		if !strings.Contains(encoded, expected) {
			t.Fatalf("typed SearchPage missing %s: %s", expected, encoded)
		}
	}
	for _, forbidden := range []string{"cards", "pageInfo", "objectType", "contentType", "label", "score", "matchedTerms", "rankReasons", "evidence", "provider", "experimentBucket", "objectId", "index", "embedding", "features"} {
		if strings.Contains(encoded, forbidden) {
			t.Fatalf("private owner field %s leaked: %s", forbidden, encoded)
		}
	}
}

func TestSearchPageExecutorRejectsEntryVariablesAndIdentityBeforeOwnerCall(t *testing.T) {
	calls := 0
	ownerServer := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { calls++ }))
	defer ownerServer.Close()
	executor := newSearchPageExecutor(t, ownerServer.URL, nil)

	for _, testCase := range []struct {
		name      string
		ctx       context.Context
		entry     domain.Entry
		variables map[string]any
	}{
		{name: "executor drift", ctx: ownerinfra.WithSearchSessionID(context.Background(), "session-1"), entry: mutateSearchPageEntry(func(entry *domain.Entry) { entry.ExecutorKey = "search.other" }), variables: validSearchPageVariables()},
		{name: "mode injection", ctx: ownerinfra.WithSearchSessionID(context.Background(), "session-1"), entry: searchPageEntry(), variables: map[string]any{"input": map[string]any{"query": "大理", "mode": "suggest"}}},
		{name: "page too large", ctx: ownerinfra.WithSearchSessionID(context.Background(), "session-1"), entry: searchPageEntry(), variables: map[string]any{"input": map[string]any{"query": "大理", "first": json.Number("21")}}},
		{name: "unknown object type", ctx: ownerinfra.WithSearchSessionID(context.Background(), "session-1"), entry: searchPageEntry(), variables: map[string]any{"input": map[string]any{"query": "大理", "objectTypes": []any{"RAW_INDEX"}}}},
		{name: "anonymous without session", ctx: context.Background(), entry: searchPageEntry(), variables: validSearchPageVariables()},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			if _, err := executor.Execute(testCase.ctx, testCase.entry, testCase.variables); err == nil {
				t.Fatal("invalid SearchPage request must fail closed")
			}
		})
	}
	if calls != 0 {
		t.Fatalf("invalid requests reached owner %d times", calls)
	}
}

func TestSearchPageExecutorPreservesAuthenticatedPrincipalForServiceOwnerCall(t *testing.T) {
	ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer account:account-1" {
			t.Fatalf("account-delegated authorization=%q", request.Header.Get("Authorization"))
		}
		if request.Header.Get("X-QWQ-Delegated-Principal-Kind") != "" ||
			request.Header.Get("X-QWQ-Delegated-Principal-Id") != "" {
			t.Fatalf("unsigned delegated principal header leaked=%v", request.Header)
		}
		writeSearchOwnerResponse(response, emptySearchOwnerResponse())
	}))
	defer ownerServer.Close()
	executor := newSearchPageExecutor(t, ownerServer.URL, nil)
	principal := rtauth.Principal{Actor: rtoperation.ActorContext{AccountID: "account-1", PersonaID: "persona-1"}}
	ctx := rtauth.WithPrincipal(context.Background(), principal)
	if _, err := executor.Execute(ctx, searchPageEntry(), validSearchPageVariables()); err != nil {
		t.Fatal(err)
	}
}

func TestSearchPageExecutorFailsClosedOnPartialOrPrivateOwnerResponse(t *testing.T) {
	for _, testCase := range []struct {
		name   string
		mutate func(map[string]any)
	}{
		{name: "partial degrade", mutate: func(response map[string]any) {
			response["degradeSignals"] = []any{map[string]any{"code": "SEARCH.MIDDLEWARE.unavailable", "message": "partial"}}
		}},
		{name: "raw index", mutate: func(response map[string]any) {
			response["hits"] = []any{map[string]any{"objectRef": "objref", "objectType": "content.post", "contentType": "article", "title": "title", "index": "private-index"}}
		}},
		{name: "missing canonical action", mutate: func(response map[string]any) {
			response["hits"] = []any{map[string]any{"objectRef": "objref", "objectType": "content.post", "title": "title"}}
		}},
		{name: "graphql errors", mutate: func(response map[string]any) { response["errors"] = []any{map[string]any{"message": "owner failed"}} }},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
				payload := emptySearchOwnerResponse()
				testCase.mutate(payload)
				writeSearchOwnerResponse(response, payload)
			}))
			defer ownerServer.Close()
			executor := newSearchPageExecutor(t, ownerServer.URL, nil)
			ctx := ownerinfra.WithSearchSessionID(context.Background(), "session-1")
			if _, err := executor.Execute(ctx, searchPageEntry(), validSearchPageVariables()); err == nil {
				t.Fatal("partial/private owner response must fail closed")
			}
		})
	}
}

func TestSearchPageExecutorCandidateWithoutOriginDoesNotFallBack(t *testing.T) {
	stableCalls := 0
	stableServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		stableCalls++
		writeSearchOwnerResponse(response, emptySearchOwnerResponse())
	}))
	defer stableServer.Close()
	executor := newSearchPageExecutor(t, stableServer.URL, nil)
	ctx := rolloutapp.WithTarget(ownerinfra.WithSearchSessionID(context.Background(), "session-1"), rolloutdomain.TargetCandidate)
	if _, err := executor.Execute(ctx, searchPageEntry(), validSearchPageVariables()); err == nil {
		t.Fatal("candidate target without candidate origin must fail closed")
	}
	if stableCalls != 0 {
		t.Fatalf("candidate failure fell back to stable %d times", stableCalls)
	}
}

func newSearchPageExecutor(t *testing.T, stableRawURL string, candidateRawURL *string) *ownerinfra.SearchPageQueryExecutor {
	t.Helper()
	stable, err := url.Parse(stableRawURL)
	if err != nil {
		t.Fatal(err)
	}
	var candidate *url.URL
	if candidateRawURL != nil {
		candidate, err = url.Parse(*candidateRawURL)
		if err != nil {
			t.Fatal(err)
		}
	}
	executor, err := ownerinfra.NewSearchPageQueryExecutor(
		stable, candidate, http.DefaultClient, "sha256:test-graph",
		staticServiceCredentials{header: "Bearer search-owner-token"},
		staticAccountCredentials{},
	)
	if err != nil {
		t.Fatal(err)
	}
	return executor
}

type staticAccountCredentials struct{}

func (staticAccountCredentials) AuthorizationHeaderForAccount(_ context.Context, accountID string) (string, error) {
	return "Bearer account:" + accountID, nil
}

func searchPageEntry() domain.Entry {
	entry := validRegistryEntry()
	entry.SHA256Hash = "894a7b1541100c4ffa20e446d7969aa6bb1c6aa385d025cc2a8c7b625ba50d58"
	entry.OperationName = "SearchPage"
	entry.CanonicalOperationID = "gateway.persisted_query_execution.SearchPage"
	entry.ObjectIDs = []string{"gateway.persisted_query_execution"}
	entry.Authorization = domain.AuthorizationBinding{Principal: "public", OwnershipPolicy: "public_search_discovery"}
	entry.ExecutorKey = "search.searchIndexView.searchPage"
	entry.Cost.Depth = 3
	entry.Cost.TopLevelFields = 1
	entry.Cost.Complexity = 208
	entry.Cost.PageSizeMax = 20
	entry.Cost.MaxOwnerCalls = 1
	entry.Cost.MaxBatchKeys = 1
	entry.Cost.MaxResponseBytes = 256 * 1024
	entry.CostPlan.BaseComplexity = 208
	entry.CostPlan.ListMultipliers = []domain.ListMultiplier{{
		VariablePath: "input.first", Coefficient: 10, DefaultValue: 20, MaximumValue: 20,
	}}
	entry.CostPlan.MaxOwnerCalls = 1
	entry.CostPlan.MaxBatchKeys = 1
	entry.CostPlan.MaxResponseBytes = 256 * 1024
	entry.PaginationVariables = []string{"input.first"}
	syncCostPlan(&entry)
	return entry
}

func mutateSearchPageEntry(mutate func(*domain.Entry)) domain.Entry {
	entry := searchPageEntry()
	mutate(&entry)
	return entry
}

func validSearchPageVariables() map[string]any {
	return map[string]any{"input": map[string]any{"query": "大理", "first": json.Number("20")}}
}

func emptySearchOwnerResponse() map[string]any {
	return map[string]any{
		"interpretedQuery": map[string]any{
			"normalized": "大理", "tokens": []any{"大理"}, "variants": []any{},
			"detectedEntities": []any{}, "detectedTags": []any{}, "selectedObjectTypes": []any{},
		},
		"hits": []any{}, "citations": []any{}, "facets": []any{}, "degradeSignals": []any{},
		"provenance": map[string]any{"source": "search_index_view", "generatedAt": "2026-08-11T00:00:00Z"},
		"nextCursor": "",
	}
}

func writeSearchOwnerResponse(response http.ResponseWriter, payload map[string]any) {
	response.Header().Set("Content-Type", "application/json; charset=utf-8")
	response.Header().Set("X-Contract-Graph-SHA256", "sha256:test-graph")
	_ = json.NewEncoder(response).Encode(payload)
}
