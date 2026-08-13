// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/multi-domain-result-composition/spec.md#gwt-002
// readiness_case: execute-search-page-persisted-graphql-api
package api_integration

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	httpadapter "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	ownerinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
)

// searchContractGraphDigest is the opaque ContractGraph binding for the
// search owner fixture; sha256("search-api-integration").
const searchContractGraphDigest = "sha256:24e5164dc0eabc29741ac9fdab438de1029d451a5ed7af1ebb9eacbb115970c6"

func TestSearchPagePersistedGraphQLExecutesTypedOwnerProjectionOverHTTP(t *testing.T) {
	ownerCalls := 0
	ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		ownerCalls++
		if request.Method != http.MethodPost || request.URL.Path != "/search" ||
			request.Header.Get("Authorization") != "Bearer search-api-integration" ||
			request.Header.Get("X-Session-Id") != "search-session-1" {
			t.Fatalf("owner request=%s %s headers=%v", request.Method, request.URL.Path, request.Header)
		}
		var body struct {
			Query string `json:"query"`
			Mode  string `json:"mode"`
			Limit int    `json:"limit"`
		}
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body.Query != "大理" || body.Mode != "result" || body.Limit != 2 {
			t.Fatalf("owner body=%+v", body)
		}
		response.Header().Set("Content-Type", "application/json")
		response.Header().Set("X-Contract-Graph-SHA256", searchContractGraphDigest)
		_ = json.NewEncoder(response).Encode(map[string]any{
			"searchRequestId": "search.req.api-1",
			"interpretedQuery": map[string]any{
				"normalized": "大理", "tokens": []string{"大理"}, "variants": []string{"洱海"},
				"detectedEntities": []string{}, "detectedTags": []string{}, "selectedObjectTypes": []string{"content.post"},
			},
			"hits": []any{map[string]any{
				"objectRef": "opaque-post-1", "objectType": "content.post", "contentType": "article",
				"title": "大理古城", "snippet": "日落路线",
				"thumbnailUrl": "https://cdn.example/post-1.webp",
				"action":       "quwoquan://content/posts/post-1",
				"rankPosition": 1,
				"matchedTerms": []string{"大理"},
				"rankReasons":  []any{map[string]any{"code": "term", "label": "标题命中", "weight": 3.0}},
				"evidence":     []any{map[string]any{"field": "title", "snippet": "大理古城"}},
			}},
			"citations": []any{}, "facets": []any{}, "degradeSignals": []any{},
			"provenance": map[string]any{"source": "search_index_view", "generatedAt": "2026-08-11T00:00:00Z"},
			"nextCursor": "",
		})
	}))
	defer ownerServer.Close()

	origin, err := url.Parse(ownerServer.URL)
	if err != nil {
		t.Fatal(err)
	}
	executor, err := ownerinfra.NewSearchPageQueryExecutor(
		origin,
		nil,
		http.DefaultClient,
		searchContractGraphDigest,
		searchAPIServiceCredential{},
		searchAPIAccountCredential{},
	)
	if err != nil {
		t.Fatal(err)
	}
	entry := searchAPIRegistryEntry()
	registry, err := domain.NewRegistry([]domain.Entry{entry})
	if err != nil {
		t.Fatal(err)
	}
	service, err := application.NewService("beta", registry, searchAPIAuthorizer{}, executor, nil)
	if err != nil {
		t.Fatal(err)
	}
	ingress := httptest.NewServer(searchAPISessionMiddleware(httpadapter.NewHandler(service)))
	defer ingress.Close()

	response := postJSON(t, ingress.URL, map[string]any{
		"operationName": "SearchPage",
		"variables": map[string]any{"input": map[string]any{
			"query": "大理", "first": 2, "objectTypes": []string{"CONTENT_POST"},
		}},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": entry.SHA256Hash},
		},
	})
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK || ownerCalls != 1 {
		t.Fatalf("status=%d ownerCalls=%d body=%s", response.StatusCode, ownerCalls, body)
	}
	if string(body) == "" || !json.Valid(body) {
		t.Fatalf("invalid GraphQL body=%s", body)
	}
	var envelope struct {
		Data struct {
			SearchPage struct {
				Items []struct {
					ObjectRef    string  `json:"objectRef"`
					ResultType   string  `json:"resultType"`
					ContentType  *string `json:"contentType"`
					Action       string  `json:"action"`
					RankPosition int     `json:"rankPosition"`
					RankReason   *string `json:"rankReason"`
				} `json:"items"`
				MatchedTerms    []string `json:"matchedTerms"`
				SearchRequestID string   `json:"searchRequestId"`
			} `json:"searchPage"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		t.Fatal(err)
	}
	if len(envelope.Data.SearchPage.Items) != 1 ||
		envelope.Data.SearchPage.Items[0].ObjectRef != "opaque-post-1" ||
		envelope.Data.SearchPage.Items[0].ResultType != "CONTENT_POST" ||
		envelope.Data.SearchPage.Items[0].ContentType == nil ||
		*envelope.Data.SearchPage.Items[0].ContentType != "ARTICLE" ||
		envelope.Data.SearchPage.Items[0].Action != "quwoquan://content/posts/post-1" ||
		envelope.Data.SearchPage.Items[0].RankPosition != 1 ||
		envelope.Data.SearchPage.Items[0].RankReason == nil ||
		envelope.Data.SearchPage.SearchRequestID != "search.req.api-1" ||
		len(envelope.Data.SearchPage.MatchedTerms) != 1 {
		t.Fatalf("typed SearchPage projection drifted: %s", body)
	}
}

func searchAPIRegistryEntry() domain.Entry {
	plan := domain.CostPlan{
		BaseComplexity: 208,
		ListMultipliers: []domain.ListMultiplier{{
			VariablePath: "input.first", Coefficient: 10, DefaultValue: 20, MaximumValue: 20,
		}},
		MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 256 * 1024,
	}
	digest, err := plan.Digest()
	if err != nil {
		panic(err)
	}
	return domain.Entry{
		SHA256Hash:    "111b715594655786eba342c5cbebe7ea1338a9cf016ed0f35f54096802583478",
		OperationName: "SearchPage", OperationType: domain.OperationTypeQuery,
		CanonicalOperationID: "gateway.persisted_query_execution.SearchPage",
		ObjectIDs:            []string{"gateway.persisted_query_execution"},
		Authorization: domain.AuthorizationBinding{
			Principal: "public", OwnershipPolicy: "public_search_discovery",
		},
		CostModelVersion: domain.CostModelVersionV1, CostPlanDigest: digest,
		Cost: domain.CostBudget{
			Depth: 3, TopLevelFields: 1, Complexity: 208,
			VariablesMaxBytes: 4096, PageSizeMax: 20,
			MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 256 * 1024,
			SLORef: "slo:search.search_index_view.Search",
		},
		CostPlan: plan, PaginationVariables: []string{"input.first"},
		ExecutorKey: "search.searchIndexView.searchPage",
	}
}

type searchAPIServiceCredential struct{}

func (searchAPIServiceCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer search-api-integration", nil
}

type searchAPIAccountCredential struct{}

func (searchAPIAccountCredential) AuthorizationHeaderForAccount(_ context.Context, accountID string) (string, error) {
	return "Bearer account:" + accountID, nil
}

type searchAPIAuthorizer struct{}

func (searchAPIAuthorizer) Authorize(_ context.Context, entry domain.Entry) error {
	return ownerinfra.ValidateSearchPageEntry(entry)
}

func searchAPISessionMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		ctx := application.WithSearchSessionID(request.Context(), "search-session-1")
		next.ServeHTTP(response, request.WithContext(ctx))
	})
}
