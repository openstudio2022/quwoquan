package auth

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/runtime/operation"
)

func TestDefaultContentGuardDoesNotGrantRetiredRolePrivileges(t *testing.T) {
	for _, roles := range [][]string{nil, {"research"}, {"production"}} {
		for _, status := range []string{"ready", "blocked"} {
			t.Run(status+"/"+fmtRoles(roles), func(t *testing.T) {
				descriptor := OperationSecurityDescriptor{
					CanonicalOperationID: "content.post.GetFeed",
					ContractGraphSHA256:  testContractGraphSHA256,
					Method:               http.MethodGet, PathTemplate: "/content/feed",
					OperationKind: "query", AuthMode: "optional",
					ActorRequirement: "none", Principal: "public", CommercialStatus: status,
				}
				handler := RequireGeneratedOperationAuthorization([]OperationSecurityDescriptor{descriptor})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
					w.WriteHeader(http.StatusNoContent)
				}))
				request := httptest.NewRequest(http.MethodGet, "/content/feed", nil)
				request.Header.Set("X-Research-Identity-Attestation", "retired-untrusted-input")
				if roles != nil {
					request = request.WithContext(WithPrincipal(request.Context(), Principal{
						Actor: operation.ActorContext{AccountID: "account-a"}, Claims: Claims{Roles: roles},
					}))
				}
				response := httptest.NewRecorder()
				handler.ServeHTTP(response, request)
				want := http.StatusNoContent
				if status == "blocked" {
					want = http.StatusForbidden
				}
				if response.Code != want {
					t.Fatalf("status=%d want=%d", response.Code, want)
				}
			})
		}
	}
}

func fmtRoles(roles []string) string {
	if len(roles) == 0 {
		return "guest"
	}
	return roles[0]
}

func TestRetiredContentAndSessionRoutesAreNotSuccessfulAliases(t *testing.T) {
	handler := RequireGeneratedOperationAuthorization([]OperationSecurityDescriptor{{
		CanonicalOperationID: "content.post.GetFeed", ContractGraphSHA256: testContractGraphSHA256,
		Method: http.MethodGet, PathTemplate: "/content/feed", OperationKind: "query",
		AuthMode: "optional", ActorRequirement: "none", Principal: "public", CommercialStatus: "ready",
	}})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Fatal("unregistered retired route reached handler")
	}))
	for _, path := range []string{"/content/research/readback", "/auth/research/session", "/auth/research/session/attestation"} {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, path, nil))
		if response.Code < 400 {
			t.Fatalf("retired route %s succeeded", path)
		}
	}
}
