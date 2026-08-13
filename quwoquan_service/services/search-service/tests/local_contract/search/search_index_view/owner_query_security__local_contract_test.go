// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-001.t6
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type ownerQueryBackendSpy struct {
	calls int
	docs  []rtsearch.Document
}

func (backend *ownerQueryBackendSpy) Name() string { return "contract_search_backend" }

func (backend *ownerQueryBackendSpy) Recall(
	_ context.Context,
	plan rtsearch.RetrievePlan,
) ([]rtsearch.RecallCandidate, error) {
	backend.calls++
	result := make([]rtsearch.RecallCandidate, 0, len(backend.docs))
	for _, document := range backend.docs {
		result = append(result, rtsearch.RecallCandidate{Document: document, BaseScore: 1})
	}
	return result, nil
}

func newOwnerSearchService(t *testing.T, backend rtsearch.RecallBackend) *application.SearchService {
	t.Helper()
	codec, err := application.NewSearchCursorCodec(
		[]byte("search-owner-query-cursor-contract-secret-32-bytes"),
	)
	if err != nil {
		t.Fatalf("new cursor codec: %v", err)
	}
	return application.NewSearchService(
		backend,
		application.WithSearchCursorCodec(codec),
	)
}

func apiEdgeOwnerCaller(principal string) application.QueryCaller {
	return application.QueryCaller{
		PrincipalKey: principal,
		ServiceName:  "api-edge",
		Scopes:       []string{"search.search_index_view.graphql.read"},
	}
}

func TestOwnerQueryRetrievalRequiresAssistantServiceBeforeRecall(t *testing.T) {
	backend := &ownerQueryBackendSpy{}
	service := newOwnerSearchService(t, backend)
	input := application.QueryInput{Query: "西湖摄影", Mode: "retrieval", Limit: 10}
	identity := application.QueryExecutionIdentity{
		CandidateDigest: "sha256:" + strings.Repeat("a", 64),
		PolicyDigest:    "sha256:" + strings.Repeat("b", 64),
	}

	for name, caller := range map[string]application.QueryCaller{
		"public": {
			PrincipalKey: "session:public-search-session",
		},
		"app-service": {
			PrincipalKey: "account:user-1|service:api-edge",
			ServiceName:  "api-edge",
			Scopes:       []string{"search.search_index_view.graphql.read"},
		},
		"assistant-without-scope": {
			PrincipalKey: "account:user-1|service:assistant-service",
			ServiceName:  "assistant-service",
		},
	} {
		t.Run(name, func(t *testing.T) {
			_, err := service.ExecuteOwnerQuery(t.Context(), input, rtsearch.Viewer{}, caller, identity)
			if !errors.Is(err, application.ErrSearchForbidden) {
				t.Fatalf("error=%v want ErrSearchForbidden", err)
			}
		})
	}
	if backend.calls != 0 {
		t.Fatalf("forbidden retrieval reached backend %d times", backend.calls)
	}

	_, err := service.ExecuteOwnerQuery(
		t.Context(),
		input,
		rtsearch.Viewer{},
		application.QueryCaller{
			PrincipalKey: "account:user-1|service:assistant-service",
			ServiceName:  "assistant-service",
			Scopes:       []string{"assistant.search.search_index_view.read"},
		},
		identity,
	)
	if err != nil {
		t.Fatalf("assistant retrieval: %v", err)
	}
	if backend.calls != 1 {
		t.Fatalf("authorized retrieval backend calls=%d want 1", backend.calls)
	}
}

func TestOwnerQueryModeIsClosedBeforeRecall(t *testing.T) {
	backend := &ownerQueryBackendSpy{}
	service := newOwnerSearchService(t, backend)
	_, err := service.ExecuteOwnerQuery(
		t.Context(),
		application.QueryInput{Query: "西湖", Mode: "semantic", Limit: 10},
		rtsearch.Viewer{},
		apiEdgeOwnerCaller("session:s1|service:api-edge"),
		application.QueryExecutionIdentity{
			CandidateDigest: "sha256:" + strings.Repeat("c", 64),
			PolicyDigest:    "sha256:" + strings.Repeat("d", 64),
		},
	)
	if !errors.Is(err, application.ErrSearchInvalid) {
		t.Fatalf("error=%v want ErrSearchInvalid", err)
	}
	if backend.calls != 0 {
		t.Fatalf("invalid mode reached backend %d times", backend.calls)
	}
}

func TestOwnerQueryCursorIsOpaqueAndBoundToAllExecutionIdentity(t *testing.T) {
	backend := &ownerQueryBackendSpy{docs: []rtsearch.Document{
		{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-a", Title: "A 西湖", Visibility: "public"},
		{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-b", Title: "B 西湖", Visibility: "public"},
		{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-c", Title: "C 西湖", Visibility: "public"},
	}}
	service := newOwnerSearchService(t, backend)
	caller := apiEdgeOwnerCaller("session:opaque-cursor-user|service:api-edge")
	identity := application.QueryExecutionIdentity{
		CandidateDigest: "sha256:" + strings.Repeat("e", 64),
		PolicyDigest:    "sha256:" + strings.Repeat("f", 64),
	}
	first, err := service.ExecuteOwnerQuery(
		t.Context(),
		application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1},
		rtsearch.Viewer{},
		caller,
		identity,
	)
	if err != nil {
		t.Fatalf("first page: %v", err)
	}
	if first.NextCursor == "" || first.NextCursor == "1" || strings.Contains(first.NextCursor, "post-") {
		t.Fatalf("cursor is not opaque: %q", first.NextCursor)
	}
	if len(first.Hits) != 1 {
		t.Fatalf("first hits=%d want 1", len(first.Hits))
	}

	second, err := service.ExecuteOwnerQuery(
		t.Context(),
		application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1, Cursor: first.NextCursor},
		rtsearch.Viewer{},
		caller,
		identity,
	)
	if err != nil {
		t.Fatalf("second page: %v", err)
	}
	if len(second.Hits) != 1 || second.Hits[0].ObjectRef == first.Hits[0].ObjectRef {
		t.Fatalf("second page did not advance exactly once: first=%#v second=%#v", first.Hits, second.Hits)
	}
	// 篡改中间字符而非末字符：base64 RawURLEncoding 非严格解码会忽略末字符的
	// trailing bits，改末字符可能解出相同字节导致 AEAD 照常通过（flaky）。
	middle := len(first.NextCursor) / 2
	tamperedByte := "A"
	if first.NextCursor[middle] == 'A' {
		tamperedByte = "B"
	}
	tamperedCursor := first.NextCursor[:middle] + tamperedByte + first.NextCursor[middle+1:]

	mutations := []struct {
		name     string
		input    application.QueryInput
		caller   application.QueryCaller
		identity application.QueryExecutionIdentity
	}{
		{"query", application.QueryInput{Query: "鼓浪屿", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1, Cursor: first.NextCursor}, caller, identity},
		{"scope", application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"video"}, Limit: 1, Cursor: first.NextCursor}, caller, identity},
		{"principal", application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1, Cursor: first.NextCursor}, apiEdgeOwnerCaller("session:other|service:api-edge"), identity},
		{"candidate", application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1, Cursor: first.NextCursor}, caller, application.QueryExecutionIdentity{CandidateDigest: "sha256:" + strings.Repeat("1", 64), PolicyDigest: identity.PolicyDigest}},
		{"policy", application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1, Cursor: first.NextCursor}, caller, application.QueryExecutionIdentity{CandidateDigest: identity.CandidateDigest, PolicyDigest: "sha256:" + strings.Repeat("2", 64)}},
		{"tamper", application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1, Cursor: tamperedCursor}, caller, identity},
		{"raw-offset", application.QueryInput{Query: "西湖", Mode: "result", ObjectTypes: []string{"content.post"}, ContentTypes: []string{"article"}, Limit: 1, Cursor: "1"}, caller, identity},
	}
	for _, mutation := range mutations {
		t.Run(mutation.name, func(t *testing.T) {
			_, err := service.ExecuteOwnerQuery(t.Context(), mutation.input, rtsearch.Viewer{}, mutation.caller, mutation.identity)
			if !errors.Is(err, application.ErrSearchCursor) {
				t.Fatalf("error=%v want ErrSearchCursor", err)
			}
		})
	}
}

func TestOwnerQueryProjectionDoesNotExposeBackendOrRankingInternals(t *testing.T) {
	backend := &ownerQueryBackendSpy{docs: []rtsearch.Document{{
		ObjectType: rtsearch.ObjectTypeContentPost,
		ObjectID:   "post-sensitive-id",
		Title:      "西湖摄影",
		Summary:    "公开摘要",
		DeepLink:   "quwoquan://content/posts/public-action-ref",
		Visibility: "public",
		Fields: map[string]string{
			"thumbnailUrl": "https://cdn.example/thumbnail.webp",
			"coverUrl":     "https://cdn.example/cover.webp",
			"rawIndex":     "must-not-leak",
		},
	}}}
	service := newOwnerSearchService(t, backend)
	response, err := service.ExecuteOwnerQuery(
		t.Context(),
		application.QueryInput{Query: "西湖", Mode: "result", Limit: 10},
		rtsearch.Viewer{},
		apiEdgeOwnerCaller("session:projection|service:api-edge"),
		application.QueryExecutionIdentity{
			CandidateDigest: "sha256:" + strings.Repeat("3", 64),
			PolicyDigest:    "sha256:" + strings.Repeat("4", 64),
		},
	)
	if err != nil {
		t.Fatalf("owner query: %v", err)
	}
	encoded, err := json.Marshal(response)
	if err != nil {
		t.Fatalf("marshal response: %v", err)
	}
	text := string(encoded)
	for _, forbidden := range []string{`"score"`, `"index"`, `"features"`, `"objectId"`, "post-sensitive-id", "must-not-leak"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("owner response leaked %q: %s", forbidden, text)
		}
	}
	for _, required := range []string{`"interpretedQuery"`, `"hits"`, `"citations"`, `"facets"`, `"degradeSignals"`, `"provenance"`, `"objectRef"`, `"nextCursor"`} {
		if !strings.Contains(text, required) {
			t.Fatalf("owner response missing %q: %s", required, text)
		}
	}
	for _, required := range []string{
		`"action":"quwoquan://content/posts/public-action-ref"`,
		`"thumbnailUrl":"https://cdn.example/thumbnail.webp"`,
	} {
		if !strings.Contains(text, required) {
			t.Fatalf("owner flat card missing %q: %s", required, text)
		}
	}
}

func TestOwnerQueryDoesNotSynthesizeMissingAction(t *testing.T) {
	backend := &ownerQueryBackendSpy{docs: []rtsearch.Document{{
		ObjectType: rtsearch.ObjectTypeEntityHomepage,
		ObjectID:   "entity-no-action",
		Title:      "西湖主页",
		URL:        "https://www.example.com/entities/entity-no-action",
		Visibility: "public",
		Fields:     map[string]string{"coverUrl": "https://cdn.example/entity-cover.webp"},
	}}}
	service := newOwnerSearchService(t, backend)
	response, err := service.ExecuteOwnerQuery(
		t.Context(),
		application.QueryInput{Query: "西湖", Mode: "result", Limit: 10},
		rtsearch.Viewer{},
		apiEdgeOwnerCaller("session:no-action|service:api-edge"),
		application.QueryExecutionIdentity{
			CandidateDigest: "sha256:" + strings.Repeat("5", 64),
			PolicyDigest:    "sha256:" + strings.Repeat("6", 64),
		},
	)
	if err != nil {
		t.Fatalf("owner query: %v", err)
	}
	encoded, err := json.Marshal(response)
	if err != nil {
		t.Fatalf("marshal response: %v", err)
	}
	text := string(encoded)
	if strings.Contains(text, `"action"`) || strings.Contains(text, "entity-no-action") {
		t.Fatalf("owner query synthesized action/raw id: %s", text)
	}
	if !strings.Contains(text, `"thumbnailUrl":"https://cdn.example/entity-cover.webp"`) {
		t.Fatalf("owner query did not use bounded cover source: %s", text)
	}
}

func TestSearchOwnerContractDeclaresOneOperationAndClosedModes(t *testing.T) {
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "../../../.."))
	read := func(relative string) string {
		t.Helper()
		value, err := os.ReadFile(filepath.Join(serviceRoot, relative))
		if err != nil {
			t.Fatalf("read %s: %v", relative, err)
		}
		return string(value)
	}
	operations := read("contracts/search/search_index_view/operations.yaml")
	fields := read("contracts/search/search_index_view/fields.yaml")
	projection := read("contracts/search/search_index_view/projections/owner_search_response_view.yaml")
	if strings.Count(operations, "operation: Search\n") != 1 || strings.Contains(operations, "graphql_queries:") {
		t.Fatalf("Search must remain one canonical operation without a duplicate GraphQL owner operation:\n%s", operations)
	}
	for _, required := range []string{
		"mode=suggest|result|retrieval",
		"assistant.search.search_index_view.read",
		"search.search_index_view.graphql.read",
		"verified service principal",
		"before executor",
	} {
		if !strings.Contains(operations, required) {
			t.Fatalf("operations missing %q", required)
		}
	}
	if strings.Contains(operations, "      scopes:\n") {
		t.Fatalf("public Search operation must not apply owner scopes to App principals:\n%s", operations)
	}
	securityStart := strings.Index(operations, "    security:\n")
	applicationStart := strings.Index(operations, "    application:\n")
	if securityStart < 0 || applicationStart <= securityStart {
		t.Fatalf("operations security/application blocks are not canonical:\n%s", operations)
	}
	securityBlock := operations[securityStart:applicationStart]
	for _, forbidden := range []string{
		"mode_authorization:", "retrieval_service:", "retrieval_required_scope:",
		"retrieval_enforcement:", "owner_projection_services:",
		"api_edge_owner_required_scope:", "owner_projection_selection:",
		"cursor_format:", "cursor_bindings:", "raw_offset:",
		"elasticsearch_search_after_exposure:",
	} {
		if strings.Contains(securityBlock, forbidden) {
			t.Fatalf("security contains non-canonical extension key %q:\n%s", forbidden, securityBlock)
		}
	}
	if !strings.Contains(fields, "values: [suggest, result, retrieval]") ||
		!strings.Contains(fields, "name: cursor") ||
		!strings.Contains(fields, "name: action") ||
		!strings.Contains(fields, "name: thumbnailUrl") ||
		!strings.Contains(fields, "绑定 normalized query、筛选 scope、可信 principal、candidate 与 active policy") ||
		!strings.Contains(fields, "禁止 raw offset/ES search_after") {
		t.Fatalf("fields do not close mode/cursor contract:\n%s", fields)
	}
	for _, forbidden := range []string{"[]CanonicalSearchHit", "CanonicalSearchProvenance", "score, type:"} {
		if strings.Contains(projection, forbidden) {
			t.Fatalf("owner projection leaked legacy/backend field %q:\n%s", forbidden, projection)
		}
	}
}

func TestOwnerQueryApplicationDoesNotImportElasticsearchTransport(t *testing.T) {
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test path")
	}
	applicationDir := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "../../../../internal/search/search_index_view/application"))
	entries, err := os.ReadDir(applicationDir)
	if err != nil {
		t.Fatalf("read application dir: %v", err)
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") {
			continue
		}
		value, err := os.ReadFile(filepath.Join(applicationDir, entry.Name()))
		if err != nil {
			t.Fatalf("read %s: %v", entry.Name(), err)
		}
		text := string(value)
		if strings.Contains(text, "runtime/search/es") || strings.Contains(text, `"/_search"`) || strings.Contains(text, "search_after") {
			t.Fatalf("owner application directly accesses Elasticsearch in %s", entry.Name())
		}
	}
}

func TestOwnerQueryHTTPBoundaryUsesEmbeddedContractGraphIdentity(t *testing.T) {
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test path")
	}
	handlerPath := filepath.Clean(filepath.Join(
		filepath.Dir(currentFile),
		"../../../../internal/search/search_index_view/adapters/inbound/http/handler.go",
	))
	source, err := os.ReadFile(handlerPath)
	if err != nil {
		t.Fatalf("read search owner handler: %v", err)
	}
	for _, required := range []string{
		`operationsecurity.ContractGraphSHA256`,
		`X-Contract-Graph-SHA256`,
		`"sha256:" + operationsecurity.ContractGraphSHA256`,
	} {
		if !strings.Contains(string(source), required) {
			t.Fatalf("Search owner handler does not bind embedded ContractGraph identity %q", required)
		}
	}
}
