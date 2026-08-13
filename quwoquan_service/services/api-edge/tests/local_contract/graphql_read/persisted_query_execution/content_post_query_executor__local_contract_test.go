// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
// readiness_case: execute-persisted-graphql-query-local
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	ownerinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
)

// testGraphContractDigest is the opaque ContractGraph binding shared by the
// executor fixtures in this package; sha256("test-graph").
const testGraphContractDigest = "sha256:3d6824ed51d9e52976552b6b912b43adaeb8dcc6abc4fc24ea915db5f2df5635"

func TestContentPostExecutorRejectsEntryAndVariableDriftBeforeOwnerCall(t *testing.T) {
	calls := 0
	ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		calls++
		writeOwnerPost(response, "contentPostDetailBase", baseOwnerPost("post-1", "title"))
	}))
	defer ownerServer.Close()
	executor := newContentPostExecutor(t, ownerServer.URL, nil)

	entryCases := []struct {
		name  string
		entry domain.Entry
	}{
		{name: "executor key", entry: mutateContentPostEntry(func(entry *domain.Entry) { entry.ExecutorKey = "content.post.other" })},
		{name: "operation", entry: mutateContentPostEntry(func(entry *domain.Entry) { entry.CanonicalOperationID = "content.post.GetFeed" })},
		{name: "object", entry: mutateContentPostEntry(func(entry *domain.Entry) { entry.ObjectIDs = []string{"content.comment"} })},
	}
	for _, testCase := range entryCases {
		t.Run(testCase.name, func(t *testing.T) {
			if _, err := executor.Execute(
				context.Background(), testCase.entry, map[string]any{"postId": "post-1"},
			); err == nil {
				t.Fatal("drifted registry binding must fail closed")
			}
		})
	}
	if _, err := executor.Execute(
		context.Background(), contentPostBaseEntry(), map[string]any{"postId": "post-1", "extra": true},
	); err == nil {
		t.Fatal("variables outside the persisted query contract must fail closed")
	}
	if calls != 0 {
		t.Fatalf("invalid entry or variables reached owner %d times", calls)
	}
}

func TestContentPostExecutorForwardsOnlyAnExactGraphQLSelection(t *testing.T) {
	ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost || request.URL.EscapedPath() != "/internal/graphql" {
			t.Errorf("owner request=%s %s", request.Method, request.URL.EscapedPath())
		}
		if got := request.Header.Get("X-Contract-Graph-SHA256"); got != testGraphContractDigest {
			t.Errorf("contract graph header=%q", got)
		}
		if got := request.Header.Get("Authorization"); got != "Bearer test-service-token" {
			t.Errorf("owner service authorization=%q", got)
		}
		assertInternalOwnerRequest(t, request)
		writeOwnerPost(response, "contentPostDetailBase", baseOwnerPost("post-1", "canonical title"))
	}))
	defer ownerServer.Close()
	executor := newContentPostExecutor(t, ownerServer.URL, nil)
	result, err := executor.Execute(
		context.Background(), contentPostBaseEntry(), map[string]any{"postId": "post-1"},
	)
	if err != nil {
		t.Fatal(err)
	}
	var data struct {
		ContentPostDetailBase map[string]any `json:"contentPostDetailBase"`
	}
	if err := json.Unmarshal(result.Data, &data); err != nil {
		t.Fatal(err)
	}
	if data.ContentPostDetailBase["postId"] != "post-1" ||
		data.ContentPostDetailBase["title"] != "canonical title" {
		t.Fatalf("projected data=%v", data.ContentPostDetailBase)
	}
	if len(data.ContentPostDetailBase) != 30 {
		t.Fatalf("GraphQL projection keys=%v", data.ContentPostDetailBase)
	}
	if liked, exists := data.ContentPostDetailBase["viewerLiked"]; !exists || liked != nil {
		t.Fatalf("public persisted read must project viewerLiked=null, got %v", liked)
	}
}

func TestContentPostExecutorExecutesEveryTypeAwareBundleSlice(t *testing.T) {
	for _, testCase := range []struct {
		operation string
		hash      string
		root      string
		payload   map[string]any
	}{
		{
			operation: "ContentPostDetailSemantic",
			hash:      "b425b396c13494d91b0e970d0e9c2328d07d549c492bd76537dace26ea74aa04",
			root:      "contentPostDetailSemantic",
			payload: map[string]any{
				"postId": "post-1", "contentType": "micro", "tagRefs": []any{},
				"entityRefs": []any{}, "semanticMentions": []any{},
			},
		},
		{
			operation: "ContentPostDetailMedia",
			hash:      "2251d9dca6cc14a77ff40eb630223df0b432095a98c7bd3f9f72d2e8d0752c18",
			root:      "contentPostDetailMedia",
			payload: map[string]any{
				"postId": "post-1", "contentType": "video", "mediaAssetIds": []any{},
				"mediaUrls": []any{}, "mediaItems": []any{}, "thumbnailUrl": nil,
				"videoUrl": nil, "width": nil, "height": nil, "durationMs": nil,
				"coverStrategy": nil, "coverFrameTimeMs": nil,
			},
		},
		{
			operation: "ContentPostDetailArticleRenderAssets",
			hash:      "119359eb546ba50284ad676377ca69138129ca01d605688310292ca156848b38",
			root:      "contentPostDetailArticleRenderAssets",
			payload: map[string]any{
				"postId": "post-1", "contentType": "article", "articleMarkdown": nil,
				"markdownDialect": nil, "articleMarkdownDigest": nil,
				"articleAssetManifestSummary": nil, "articleAssets": []any{},
				"articleRenderProfileSummary": nil, "contentVertical": nil,
				"articleTemplate": nil, "articleFontPreset": nil,
			},
		},
		{
			operation: "ContentPostDetailArticleEntities",
			hash:      "c9206041dca121c2df985c47f57601ccbc256047ade5e4496b2274fd9f9d02fa",
			root:      "contentPostDetailArticleEntities",
			payload: map[string]any{
				"postId": "post-1", "contentType": "article", "entityMentions": []any{},
			},
		},
	} {
		t.Run(testCase.operation, func(t *testing.T) {
			ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
				var requestPayload struct {
					OperationName string `json:"operationName"`
				}
				if err := json.NewDecoder(request.Body).Decode(&requestPayload); err != nil {
					t.Fatal(err)
				}
				if requestPayload.OperationName != testCase.operation {
					t.Fatalf("operation=%q", requestPayload.OperationName)
				}
				writeOwnerPost(response, testCase.root, testCase.payload)
			}))
			defer ownerServer.Close()
			executor := newContentPostExecutor(t, ownerServer.URL, nil)
			result, err := executor.Execute(context.Background(), contentPostBundleEntry(testCase.operation, testCase.hash), map[string]any{"postId": "post-1"})
			if err != nil {
				t.Fatal(err)
			}
			if !strings.Contains(string(result.Data), `"`+testCase.root+`"`) {
				t.Fatalf("response=%s", result.Data)
			}
		})
	}
}

func TestContentPostExecutorRejectsBundleSliceForAnotherContentType(t *testing.T) {
	payload := map[string]any{
		"postId": "post-1", "contentType": "image", "articleMarkdown": nil,
		"markdownDialect": nil, "articleMarkdownDigest": nil,
		"articleAssetManifestSummary": nil, "articleAssets": []any{},
		"articleRenderProfileSummary": nil, "contentVertical": nil,
		"articleTemplate": nil, "articleFontPreset": nil,
	}
	ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		writeOwnerPost(response, "contentPostDetailArticleRenderAssets", payload)
	}))
	defer ownerServer.Close()
	executor := newContentPostExecutor(t, ownerServer.URL, nil)
	if _, err := executor.Execute(
		context.Background(),
		contentPostBundleEntry("ContentPostDetailArticleRenderAssets", "119359eb546ba50284ad676377ca69138129ca01d605688310292ca156848b38"),
		map[string]any{"postId": "post-1"},
	); err == nil {
		t.Fatal("article extension accepted image content")
	}
}

func TestContentPostExecutorRejectsInvalidOwnerResponses(t *testing.T) {
	for _, testCase := range []struct {
		name        string
		status      int
		contentType string
		body        string
	}{
		{name: "status", status: http.StatusServiceUnavailable, contentType: "application/json", body: `{}`},
		{name: "content type", status: http.StatusOK, contentType: "text/plain", body: `{}`},
		{name: "missing required", status: http.StatusOK, contentType: "application/json", body: `{"data":{"contentPostDetailBase":{"postId":"post-1"}}}`},
		{name: "wrong post", status: http.StatusOK, contentType: "application/json", body: validOwnerGraphQLJSON("post-2")},
		{name: "extra owner field", status: http.StatusOK, contentType: "application/json", body: ownerGraphQLJSON("contentPostDetailBase", withField(baseOwnerPost("post-1", "canonical title"), "storageSecret", "must-not-leak"))},
		{name: "trailing json", status: http.StatusOK, contentType: "application/json", body: validOwnerGraphQLJSON("post-1") + `{}`},
		{name: "oversized body", status: http.StatusOK, contentType: "application/json", body: strings.Repeat("x", 4*1024*1024+1)},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			ownerServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
				response.Header().Set("Content-Type", testCase.contentType)
				response.Header().Set("X-Contract-Graph-SHA256", testGraphContractDigest)
				response.WriteHeader(testCase.status)
				_, _ = response.Write([]byte(testCase.body))
			}))
			defer ownerServer.Close()
			executor := newContentPostExecutor(t, ownerServer.URL, nil)
			if _, err := executor.Execute(
				context.Background(), contentPostBaseEntry(), map[string]any{"postId": "post-1"},
			); err == nil {
				t.Fatal("invalid owner response must fail closed")
			}
		})
	}
}

func TestContentPostExecutorRequiresTrustedServiceCredentials(t *testing.T) {
	stable, err := url.Parse("https://content.example")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ownerinfra.NewContentPostQueryExecutor(
		stable,
		nil,
		http.DefaultClient,
		testGraphContractDigest,
		nil,
	); err == nil {
		t.Fatal("production owner executor without service credentials must fail closed")
	}

	calls := 0
	ownerServer := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		calls++
	}))
	defer ownerServer.Close()
	origin, err := url.Parse(ownerServer.URL)
	if err != nil {
		t.Fatal(err)
	}
	executor, err := ownerinfra.NewContentPostQueryExecutor(
		origin,
		nil,
		http.DefaultClient,
		testGraphContractDigest,
		staticServiceCredentials{header: "not-a-bearer"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := executor.Execute(
		context.Background(), contentPostBaseEntry(), map[string]any{"postId": "post-1"},
	); err == nil {
		t.Fatal("invalid service authorization header must fail closed")
	}
	if calls != 0 {
		t.Fatalf("invalid service credentials reached owner %d times", calls)
	}
}

func TestContentPostExecutorCandidateWithoutOriginDoesNotFallBack(t *testing.T) {
	stableCalls := 0
	stableServer := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		stableCalls++
		writeOwnerPost(response, "contentPostDetailBase", baseOwnerPost("post-1", "title"))
	}))
	defer stableServer.Close()
	executor := newContentPostExecutor(t, stableServer.URL, nil)
	ctx := rolloutapp.WithTarget(context.Background(), rolloutdomain.TargetCandidate)
	if _, err := executor.Execute(
		ctx, contentPostBaseEntry(), map[string]any{"postId": "post-1"},
	); err == nil {
		t.Fatal("candidate target without candidate origin must fail closed")
	}
	if stableCalls != 0 {
		t.Fatalf("candidate failure fell back to stable %d times", stableCalls)
	}
}

func mutateContentPostEntry(mutate func(*domain.Entry)) domain.Entry {
	entry := contentPostBaseEntry()
	mutate(&entry)
	return entry
}

func newContentPostExecutor(
	t *testing.T,
	stableRawURL string,
	candidateRawURL *string,
) *ownerinfra.ContentPostQueryExecutor {
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
	executor, err := ownerinfra.NewContentPostQueryExecutor(
		stable, candidate, http.DefaultClient, testGraphContractDigest,
		staticServiceCredentials{header: "Bearer test-service-token"},
	)
	if err != nil {
		t.Fatal(err)
	}
	return executor
}

func writeOwnerPost(response http.ResponseWriter, rootField string, payload map[string]any) {
	response.Header().Set("Content-Type", "application/json; charset=utf-8")
	response.Header().Set("X-Contract-Graph-SHA256", testGraphContractDigest)
	_ = json.NewEncoder(response).Encode(map[string]any{
		"data": map[string]any{rootField: payload},
	})
}

func validOwnerGraphQLJSON(postID string) string {
	return ownerGraphQLJSON("contentPostDetailBase", baseOwnerPost(postID, "canonical title"))
}

func assertInternalOwnerRequest(t *testing.T, request *http.Request) {
	t.Helper()
	var payload struct {
		OperationName string         `json:"operationName"`
		Variables     map[string]any `json:"variables"`
		Extensions    struct {
			PersistedQuery struct {
				Version    int    `json:"version"`
				SHA256Hash string `json:"sha256Hash"`
			} `json:"persistedQuery"`
		} `json:"extensions"`
		Query *string `json:"query"`
	}
	if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.OperationName != "ContentPostDetailBase" ||
		payload.Variables["postId"] != "post-1" ||
		payload.Extensions.PersistedQuery.Version != 1 ||
		payload.Extensions.PersistedQuery.SHA256Hash != contentPostBaseEntry().SHA256Hash ||
		payload.Query != nil {
		t.Fatalf("owner persisted request=%+v", payload)
	}
}

func contentPostBaseEntry() domain.Entry {
	entry := validRegistryEntry()
	entry.SHA256Hash = "3525412614f94647191c1fead96cc6da3bdc452bf0bec9edd92af4793aed3110"
	entry.OperationName = "ContentPostDetailBase"
	entry.Cost.Depth = 3
	entry.Cost.Complexity = 56
	entry.Cost.PageSizeMax = 1
	entry.Cost.MaxResponseBytes = 64 * 1024
	entry.CostPlan.BaseComplexity = 56
	entry.CostPlan.MaxResponseBytes = 64 * 1024
	syncCostPlan(&entry)
	return entry
}

func contentPostBundleEntry(operationName, hash string) domain.Entry {
	entry := contentPostBaseEntry()
	entry.OperationName = operationName
	entry.SHA256Hash = hash
	entry.CanonicalOperationID = map[string]string{
		"ContentPostDetailBase":                "content.post.GetPost",
		"ContentPostDetailSemantic":            "content.post.GetPostSemantic",
		"ContentPostDetailMedia":               "content.post.GetPostMedia",
		"ContentPostDetailArticleRenderAssets": "content.post.GetPostArticleRenderAssets",
		"ContentPostDetailArticleEntities":     "content.post.GetPostArticleEntities",
	}[operationName]
	return entry
}

func baseOwnerPost(postID, title string) map[string]any {
	return map[string]any{
		"postId": postID, "contentType": "article", "contentIdentity": nil,
		"assistantUsePolicy": nil, "authorId": nil, "authorDisplayName": nil,
		"authorAvatarUrl": nil, "title": title, "body": nil, "summary": nil,
		"coverUrl": nil, "sourceAttribution": nil, "location": nil,
		"locationName": nil, "geoTagRef": nil, "visitedAt": nil,
		"primaryHomepageId": nil, "canonicalEntityId": nil, "primaryHomepageType": nil,
		"primaryHomepageSnapshot": nil, "status": "published", "visibility": "public",
		"likeCount": 1, "commentCount": 2, "shareCount": 3, "viewCount": 4, "viewerLiked": nil,
		"createdAt": "2026-08-11T00:00:00Z", "updatedAt": "2026-08-11T00:01:00Z",
		"publishedAt": nil,
	}
}

func withField(value map[string]any, key string, field any) map[string]any {
	copy := make(map[string]any, len(value)+1)
	for name, item := range value {
		copy[name] = item
	}
	copy[key] = field
	return copy
}

func ownerGraphQLJSON(root string, value map[string]any) string {
	payload, _ := json.Marshal(map[string]any{"data": map[string]any{root: value}})
	return string(payload)
}

type staticServiceCredentials struct{ header string }

func (credentials staticServiceCredentials) AuthorizationHeader(context.Context) (string, error) {
	return credentials.header, nil
}
