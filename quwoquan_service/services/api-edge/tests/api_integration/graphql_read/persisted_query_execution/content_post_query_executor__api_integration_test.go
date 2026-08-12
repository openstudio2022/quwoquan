// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
// readiness_case: execute-persisted-graphql-query-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	httpadapter "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	ownerinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
)

func TestPersistedGraphQLSelectsStableAndCandidateContentOwners(t *testing.T) {
	stableCalls := 0
	candidateCalls := 0
	stable := newGraphQLOwner(t, "stable", &stableCalls)
	defer stable.Close()
	candidate := newGraphQLOwner(t, "candidate", &candidateCalls)
	defer candidate.Close()

	executor := newGraphQLContentExecutor(t, stable.URL, candidate.URL)
	entry := contentPostEntry()
	registry, err := domain.NewRegistry([]domain.Entry{entry})
	if err != nil {
		t.Fatal(err)
	}
	service, err := application.NewService("beta", registry, exactBindingAuthorizer{}, executor, nil)
	if err != nil {
		t.Fatal(err)
	}
	ingress := httptest.NewServer(targetTestMiddleware(httpadapter.NewHandler(service)))
	defer ingress.Close()

	stableResponse := postGraphQLTarget(t, ingress.URL, "stable", entry.SHA256Hash)
	assertGraphQLOwnerResponse(t, stableResponse, "stable")
	candidateResponse := postGraphQLTarget(t, ingress.URL, "candidate", entry.SHA256Hash)
	assertGraphQLOwnerResponse(t, candidateResponse, "candidate")
	if stableCalls != 1 || candidateCalls != 1 {
		t.Fatalf("stable calls=%d candidate calls=%d", stableCalls, candidateCalls)
	}
}

func newGraphQLOwner(t *testing.T, title string, calls *int) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		(*calls)++
		if request.Method != http.MethodPost || request.URL.Path != "/internal/graphql" {
			t.Errorf("owner request=%s %s", request.Method, request.URL.Path)
		}
		if request.Header.Get("X-Contract-Graph-SHA256") != "sha256:api-integration" {
			t.Errorf("missing ContractGraph binding")
		}
		if request.Header.Get("Authorization") != "Bearer graphql-api-integration" {
			t.Errorf("missing service credential")
		}
		response.Header().Set("Content-Type", "application/json")
		response.Header().Set("X-Contract-Graph-SHA256", "sha256:api-integration")
		payload := apiBaseOwnerPost(title)
		_ = json.NewEncoder(response).Encode(map[string]any{
			"data": map[string]any{"contentPostDetailBase": payload},
		})
	}))
}

func newGraphQLContentExecutor(
	t *testing.T,
	stableRawURL string,
	candidateRawURL string,
) *ownerinfra.ContentPostQueryExecutor {
	t.Helper()
	stable, err := url.Parse(stableRawURL)
	if err != nil {
		t.Fatal(err)
	}
	var candidate *url.URL
	if candidateRawURL != "" {
		candidate, err = url.Parse(candidateRawURL)
		if err != nil {
			t.Fatal(err)
		}
	}
	executor, err := ownerinfra.NewContentPostQueryExecutor(
		stable,
		candidate,
		http.DefaultClient,
		"sha256:api-integration",
		contentOwnerServiceCredential{},
	)
	if err != nil {
		t.Fatal(err)
	}
	return executor
}

func contentPostEntry() domain.Entry {
	plan := domain.CostPlan{
		BaseComplexity: 56, ListMultipliers: []domain.ListMultiplier{},
		MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 64 * 1024,
	}
	digest, err := plan.Digest()
	if err != nil {
		panic(err)
	}
	return domain.Entry{
		SHA256Hash:           "3c1481366f84401aa2d89280925d5943bf040f7c94cf757fb5cc219f00a7f71b",
		OperationName:        "ContentPostDetailBase",
		OperationType:        domain.OperationTypeQuery,
		CanonicalOperationID: "content.post.GetPost",
		ObjectIDs:            []string{"content.post"},
		Authorization: domain.AuthorizationBinding{
			Principal: "public", OwnershipPolicy: "visibility_filtered",
		},
		CostModelVersion: domain.CostModelVersionV1,
		CostPlanDigest:   digest,
		Cost: domain.CostBudget{
			Depth: 3, TopLevelFields: 1, Complexity: 56,
			VariablesMaxBytes: 1024, PageSizeMax: 1,
			MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 64 * 1024,
			SLORef: "slo:gateway_graphql_read_detail",
		},
		CostPlan:    plan,
		ExecutorKey: "content.post.getPost",
	}
}

type contentOwnerServiceCredential struct{}

func (contentOwnerServiceCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer graphql-api-integration", nil
}

func targetTestMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		target := rolloutdomain.TargetStable
		if request.Header.Get("X-Test-Rollout-Target") == "candidate" {
			target = rolloutdomain.TargetCandidate
		}
		ctx := rolloutapp.WithTarget(request.Context(), target)
		next.ServeHTTP(response, request.WithContext(ctx))
	})
}

func postGraphQLTarget(
	t *testing.T,
	endpoint string,
	target string,
	hash string,
) *http.Response {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"operationName": "ContentPostDetailBase",
		"variables":     map[string]any{"postId": "post-1"},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": hash},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Test-Rollout-Target", target)
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	return response
}

func assertGraphQLOwnerResponse(t *testing.T, response *http.Response, wantTitle string) {
	t.Helper()
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.StatusCode, body)
	}
	var wire struct {
		Data struct {
			ContentPostDetailBase map[string]any `json:"contentPostDetailBase"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &wire); err != nil {
		t.Fatal(err)
	}
	if wire.Data.ContentPostDetailBase["title"] != wantTitle {
		t.Fatalf("owner title=%v want=%q body=%s", wire.Data.ContentPostDetailBase["title"], wantTitle, body)
	}
	if _, leaked := wire.Data.ContentPostDetailBase["ownerPrivateField"]; leaked {
		t.Fatalf("private owner field leaked: %s", body)
	}
}

func apiBaseOwnerPost(title string) map[string]any {
	return map[string]any{
		"postId": "post-1", "contentType": "article", "contentIdentity": nil,
		"assistantUsePolicy": nil, "authorId": nil, "authorDisplayName": nil,
		"authorAvatarUrl": nil, "title": title, "body": nil, "summary": nil,
		"coverUrl": nil, "sourceAttribution": nil, "location": nil,
		"locationName": nil, "geoTagRef": nil, "visitedAt": nil,
		"primaryHomepageId": nil, "canonicalEntityId": nil, "primaryHomepageType": nil,
		"primaryHomepageSnapshot": nil, "status": "published", "visibility": "public",
		"likeCount": 1, "commentCount": 2, "shareCount": 3, "viewCount": 4,
		"createdAt": "2026-08-11T00:00:00Z", "updatedAt": "2026-08-11T00:01:00Z",
		"publishedAt": nil,
	}
}
