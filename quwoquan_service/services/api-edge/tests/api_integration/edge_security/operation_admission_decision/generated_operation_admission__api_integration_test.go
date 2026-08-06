// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-004
// readiness_case: generated-operation-admission-api
package api_integration

import (
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/api-edge/internal/edge_security/operation_admission_decision/application"
	"quwoquan_service/services/api-edge/internal/edge_security/operation_admission_decision/infrastructure"
)

func TestGeneratedOperationAdmissionAllowsKnownAndRejectsUnknownRoutes(t *testing.T) {
	descriptor := rtauth.OperationSecurityDescriptor{
		CanonicalOperationID: "content.post.GetPost",
		ContractGraphSHA256:  "operation-admission-api-integration",
		Method:               http.MethodGet,
		PathTemplate:         "/content/posts/{postId}",
		OperationKind:        "query",
		AuthMode:             "public",
		ActorRequirement:     "none",
		CommercialStatus:     "ready",
		TimeoutMilliseconds:  1000,
	}
	var ownerCalls atomic.Int64
	owner := http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		resolved, ok := rtauth.OperationDescriptorFromContext(request.Context())
		if !ok {
			t.Error("owner request is missing the generated operation descriptor")
		} else if resolved.CanonicalOperationID != descriptor.CanonicalOperationID {
			t.Errorf(
				"owner operation=%q, want %q",
				resolved.CanonicalOperationID,
				descriptor.CanonicalOperationID,
			)
		}
		ownerCalls.Add(1)
		response.WriteHeader(http.StatusNoContent)
	})
	facade := application.NewFacade(
		infrastructure.NewGeneratedOperationPort(
			[]rtauth.OperationSecurityDescriptor{descriptor},
		),
	)
	server := httptest.NewServer(facade.Wrap(owner))
	t.Cleanup(server.Close)

	known, err := server.Client().Get(server.URL + "/content/posts/post-1")
	if err != nil {
		t.Fatalf("known operation request: %v", err)
	}
	_ = known.Body.Close()
	if known.StatusCode != http.StatusNoContent {
		t.Fatalf("known operation status=%d, want %d", known.StatusCode, http.StatusNoContent)
	}

	unknown, err := server.Client().Get(server.URL + "/unregistered")
	if err != nil {
		t.Fatalf("unknown operation request: %v", err)
	}
	_ = unknown.Body.Close()
	if unknown.StatusCode != http.StatusNotFound {
		t.Fatalf("unknown operation status=%d, want %d", unknown.StatusCode, http.StatusNotFound)
	}
	if calls := ownerCalls.Load(); calls != 1 {
		t.Fatalf("owner calls=%d, want 1", calls)
	}
}

func TestGeneratedOperationAdmissionRejectsAnonymousHTTPInvocation(t *testing.T) {
	descriptor := rtauth.OperationSecurityDescriptor{
		CanonicalOperationID: "content.post.GetPost",
		ContractGraphSHA256:  "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Method:               http.MethodGet,
		PathTemplate:         "/content/posts/{postId}",
		OperationKind:        "query",
		AuthMode:             "required",
		ActorRequirement:     "persona",
		Principal:            "persona",
		OwnershipPolicy:      "requester_self",
		TimeoutMilliseconds:  1500,
		CommercialStatus:     "ready",
	}
	facade := application.NewFacade(
		infrastructure.NewGeneratedOperationPort(
			[]rtauth.OperationSecurityDescriptor{descriptor},
		),
	)
	server := httptest.NewServer(
		facade.Wrap(http.HandlerFunc(
			func(http.ResponseWriter, *http.Request) {
				t.Fatal("anonymous request reached operation owner")
			},
		)),
	)
	defer server.Close()

	response, err := server.Client().Get(server.URL + "/content/posts/post-1")
	if err != nil {
		t.Fatalf("invoke admission boundary: %v", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf(
			"status=%d want=%d",
			response.StatusCode,
			http.StatusUnauthorized,
		)
	}
}
