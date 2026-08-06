// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-004
// readiness_case: generated-operation-admission-local
package operation_admission_decision_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	admissionhttp "quwoquan_service/services/api-edge/internal/edge_security/operation_admission_decision/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/edge_security/operation_admission_decision/application"
	"quwoquan_service/services/api-edge/internal/edge_security/operation_admission_decision/infrastructure"
)

type recordingOperationAdmissionPort struct {
	wrapCalls int
}

func (port *recordingOperationAdmissionPort) Wrap(next http.Handler) http.Handler {
	port.wrapCalls++
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		response.Header().Set("X-Operation-Admission", "evaluated")
		next.ServeHTTP(response, request)
	})
}

func TestOperationAdmissionMiddlewareDelegatesThroughFacadeToTypedExternalPort(t *testing.T) {
	port := &recordingOperationAdmissionPort{}
	middleware := admissionhttp.NewMiddleware(application.NewFacade(port))
	ownerReached := false
	handler := middleware.Wrap(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		ownerReached = true
		response.WriteHeader(http.StatusNoContent)
	}))

	response := httptest.NewRecorder()
	handler.ServeHTTP(
		response,
		httptest.NewRequest(http.MethodGet, "/content/posts/post-1", nil),
	)

	if port.wrapCalls != 1 {
		t.Fatalf("external port wrap calls=%d, want 1", port.wrapCalls)
	}
	if !ownerReached {
		t.Fatal("typed external port did not continue to the owner")
	}
	if response.Code != http.StatusNoContent {
		t.Fatalf("status=%d, want %d", response.Code, http.StatusNoContent)
	}
	if value := response.Header().Get("X-Operation-Admission"); value != "evaluated" {
		t.Fatalf("operation admission marker=%q, want evaluated", value)
	}
}

func blockedDescriptor() rtauth.OperationSecurityDescriptor {
	return rtauth.OperationSecurityDescriptor{
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
		CommercialStatus:     "blocked",
	}
}

func TestOperationAdmissionPortKeepsUnknownAndBlockedOperationsFailClosed(
	t *testing.T,
) {
	reachedOwner := 0
	middleware := admissionhttp.NewMiddleware(
		application.NewFacade(
			infrastructure.NewGeneratedOperationPort(
				[]rtauth.OperationSecurityDescriptor{blockedDescriptor()},
			),
		),
	)
	handler := middleware.Wrap(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		reachedOwner++
	}))

	for _, testCase := range []struct {
		name       string
		path       string
		wantStatus int
		wantCode   string
		wantMsg    string
	}{
		{
			name:       "unknown route",
			path:       "/unregistered",
			wantStatus: http.StatusNotFound,
			wantCode:   "GATEWAY.USER.route_not_found",
			wantMsg:    "接口不存在或已下线",
		},
		{
			name:       "commercially blocked operation",
			path:       "/content/posts/post-1",
			wantStatus: http.StatusForbidden,
			wantCode:   "GATEWAY.USER.forbidden",
			wantMsg:    "当前账号没有该操作权限",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			response := httptest.NewRecorder()
			handler.ServeHTTP(
				response,
				httptest.NewRequest(http.MethodGet, testCase.path, nil),
			)
			assertGatewayRuntimeError(
				t,
				response,
				testCase.wantStatus,
				testCase.wantCode,
				testCase.wantMsg,
			)
		})
	}
	if reachedOwner != 0 {
		t.Fatalf("owner reached %d time(s), want 0", reachedOwner)
	}
}

func assertGatewayRuntimeError(
	t *testing.T,
	response *httptest.ResponseRecorder,
	wantStatus int,
	wantCode string,
	wantMsg string,
) {
	t.Helper()
	if response.Code != wantStatus {
		t.Fatalf(
			"status=%d want=%d body=%s",
			response.Code,
			wantStatus,
			response.Body.String(),
		)
	}
	var body rterr.ErrorResponse
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode runtime error: %v body=%s", err, response.Body.String())
	}
	if body.Code != wantCode {
		t.Fatalf("code=%q want=%q", body.Code, wantCode)
	}
	if body.UserMessage != wantMsg {
		t.Fatalf("userMessage=%q want=%q", body.UserMessage, wantMsg)
	}
}
