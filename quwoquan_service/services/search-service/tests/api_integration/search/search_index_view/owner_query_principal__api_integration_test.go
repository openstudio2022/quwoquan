package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	rtsearch "quwoquan_service/runtime/search"
	searchhttp "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type principalGateBackend struct {
	calls int
	docs  []rtsearch.Document
}

const contractGraphHeader = "X-Contract-Graph-SHA256"

func currentContractGraphDigest() string {
	return "sha256:" + operationsecurity.ContractGraphSHA256
}

func (backend *principalGateBackend) Name() string { return "principal_gate_backend" }
func (backend *principalGateBackend) Recall(context.Context, rtsearch.RetrievePlan) ([]rtsearch.RecallCandidate, error) {
	backend.calls++
	result := make([]rtsearch.RecallCandidate, 0, len(backend.docs))
	for _, document := range backend.docs {
		result = append(result, rtsearch.RecallCandidate{Document: document, BaseScore: 1})
	}
	return result, nil
}

func TestRetrievalModeRejectsPublicAndForeignServiceBeforeExecutor(t *testing.T) {
	for name, principal := range map[string]*rtauth.Principal{
		"public": nil,
		"api-edge": {
			Claims: rtauth.Claims{Subject: "service:api-edge", Scope: "search.search_index_view.graphql.read"},
			Actor:  rtoperation.ActorContext{AccountID: "service:api-edge"},
		},
	} {
		t.Run(name, func(t *testing.T) {
			backend := &principalGateBackend{}
			handler := newPrincipalGateHandler(t, backend)
			request := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(`{"query":"西湖","mode":"retrieval"}`))
			request.Header.Set(searchhttp.SearchSessionIDHeader, "principal-gate-session")
			if principal != nil {
				request = request.WithContext(rtauth.WithPrincipal(request.Context(), *principal))
				request.Header.Set(contractGraphHeader, currentContractGraphDigest())
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusForbidden {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
			if backend.calls != 0 {
				t.Fatalf("forbidden retrieval reached backend %d times", backend.calls)
			}
		})
	}
}

func TestRetrievalModeAllowsScopedAssistantServicePrincipal(t *testing.T) {
	backend := &principalGateBackend{docs: []rtsearch.Document{{
		ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-private-storage-id",
		Title: "西湖摄影", DeepLink: "quwoquan://content/posts/public-search-ref", Visibility: "public",
		Fields: map[string]string{"coverUrl": "https://cdn.example/search-cover.webp"},
	}}}
	handler := newPrincipalGateHandler(t, backend)
	request := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(`{"query":"西湖","mode":"retrieval"}`))
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			Subject: "service:assistant-service",
			Scope:   "assistant.search.search_index_view.read",
		},
		Actor: rtoperation.ActorContext{AccountID: "service:assistant-service"},
	}))
	request.Header.Set(contractGraphHeader, currentContractGraphDigest())
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if backend.calls != 1 {
		t.Fatalf("assistant retrieval backend calls=%d want 1", backend.calls)
	}
	body := response.Body.String()
	for _, required := range []string{
		`"interpretedQuery"`, `"objectRef"`, `"provenance"`, `"nextCursor"`,
		`"action":"quwoquan://content/posts/public-search-ref"`,
		`"thumbnailUrl":"https://cdn.example/search-cover.webp"`,
	} {
		if !strings.Contains(body, required) {
			t.Fatalf("owner retrieval response missing %s: %s", required, body)
		}
	}
	for _, forbidden := range []string{`"score"`, `"objectId"`, `"provider"`, "post-private-storage-id"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("owner retrieval response leaked %s: %s", forbidden, body)
		}
	}
}

func TestAPIEdgeOwnerProjectionRequiresVerifiedScopedPrincipal(t *testing.T) {
	t.Run("scoped", func(t *testing.T) {
		backend := &principalGateBackend{docs: []rtsearch.Document{{
			ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: "entity-internal-id",
			Title: "西湖主页", Visibility: "public",
		}}}
		handler := newPrincipalGateHandler(t, backend)
		request := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(`{"query":"西湖","mode":"result"}`))
		request.Header.Set(searchhttp.SearchSessionIDHeader, "api-edge-session")
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Claims: rtauth.Claims{Subject: "service:api-edge", Scope: "search.search_index_view.graphql.read"},
			Actor:  rtoperation.ActorContext{AccountID: "service:api-edge"},
		}))
		request.Header.Set(contractGraphHeader, currentContractGraphDigest())
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"objectRef"`) || strings.Contains(response.Body.String(), `"score"`) {
			t.Fatalf("scoped API Edge did not receive owner projection: status=%d body=%s", response.Code, response.Body.String())
		}
	})

	t.Run("missing-scope", func(t *testing.T) {
		backend := &principalGateBackend{}
		handler := newPrincipalGateHandler(t, backend)
		request := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(`{"query":"西湖","mode":"result"}`))
		request.Header.Set(searchhttp.SearchSessionIDHeader, "api-edge-session")
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Claims: rtauth.Claims{Subject: "service:api-edge"},
			Actor:  rtoperation.ActorContext{AccountID: "service:api-edge"},
		}))
		request.Header.Set(contractGraphHeader, currentContractGraphDigest())
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusForbidden || backend.calls != 0 {
			t.Fatalf("unscoped API Edge must fail before backend: status=%d calls=%d body=%s", response.Code, backend.calls, response.Body.String())
		}
	})

	t.Run("forged-header-stays-public", func(t *testing.T) {
		backend := &principalGateBackend{}
		handler := newPrincipalGateHandler(t, backend)
		request := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(`{"query":"西湖","mode":"result"}`))
		request.Header.Set(searchhttp.SearchSessionIDHeader, "public-session")
		request.Header.Set("X-Service-Actor", "api-edge")
		request.Header.Set("X-Service-Scope", "search.search_index_view.graphql.read")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"requestId"`) || strings.Contains(response.Body.String(), `"objectRef"`) {
			t.Fatalf("unverified headers selected owner projection: status=%d body=%s", response.Code, response.Body.String())
		}
	})
}

func TestOwnerQueryRequiresExactContractGraphIdentityBeforeExecutor(t *testing.T) {
	for _, testCase := range []struct {
		name           string
		requestDigest  string
		wantStatus     int
		wantCalls      int
		wantResponseID bool
	}{
		{name: "missing", wantStatus: http.StatusBadRequest},
		{name: "foreign", requestDigest: "sha256:" + strings.Repeat("f", 64), wantStatus: http.StatusBadRequest},
		{name: "exact", requestDigest: currentContractGraphDigest(), wantStatus: http.StatusOK, wantCalls: 1, wantResponseID: true},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			backend := &principalGateBackend{docs: []rtsearch.Document{{
				ObjectType: rtsearch.ObjectTypeEntityHomepage,
				ObjectID:   "entity-contract-graph-bound",
				Title:      "西湖主页",
				Visibility: "public",
			}}}
			handler := newPrincipalGateHandler(t, backend)
			request := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(`{"query":"西湖","mode":"result"}`))
			request.Header.Set(searchhttp.SearchSessionIDHeader, "contract-graph-session")
			if testCase.requestDigest != "" {
				request.Header.Set(contractGraphHeader, testCase.requestDigest)
			}
			request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
				Claims: rtauth.Claims{Subject: "service:api-edge", Scope: "search.search_index_view.graphql.read"},
				Actor:  rtoperation.ActorContext{AccountID: "service:api-edge"},
			}))
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != testCase.wantStatus || backend.calls != testCase.wantCalls {
				t.Fatalf("status=%d calls=%d body=%s", response.Code, backend.calls, response.Body.String())
			}
			if got := response.Header().Get(contractGraphHeader); testCase.wantResponseID {
				if got != currentContractGraphDigest() {
					t.Fatalf("response ContractGraph digest=%q", got)
				}
			} else if got != "" {
				t.Fatalf("blocked response leaked ContractGraph acceptance header=%q", got)
			}
		})
	}
}

func newPrincipalGateHandler(t *testing.T, backend rtsearch.RecallBackend) http.Handler {
	t.Helper()
	codec, err := application.NewSearchCursorCodec([]byte("search-api-principal-gate-contract-secret-32-bytes"))
	if err != nil {
		t.Fatalf("new cursor codec: %v", err)
	}
	experiments, err := application.NewExperiments(testAssignmentPublisher{})
	if err != nil {
		t.Fatalf("new experiments: %v", err)
	}
	if err := experiments.ApplyPolicy(application.ExperimentPolicy{
		ID: application.SearchRankingExperimentID, Revision: 1, Status: "running",
		Variants: []application.ExperimentPolicyVariant{
			{Key: application.BucketControl, AllocationBasisPoints: 5000},
			{Key: application.BucketTermHeat, AllocationBasisPoints: 5000},
		},
		UpdatedAt: "2026-08-11T00:00:00Z",
	}); err != nil {
		t.Fatalf("apply policy: %v", err)
	}
	service := application.NewSearchService(backend, application.WithSearchCursorCodec(codec))
	return searchhttp.NewHandlerWithConfig(
		service,
		application.NewRankingDecorator(nil, experiments, 0, nil),
		nil,
		searchhttp.HandlerConfig{CandidateDigest: "sha256:" + strings.Repeat("9", 64)},
	).Routes()
}
