package auth

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
//
// 研究态能力面收敛（DEC-032）：research 身份由服务端签发的 principal role 承载，
// guard 对含 research role 的已验签 principal 只放行研究能力闭集——ready 只读
// 投影、session kind 与具名 research 操作；写操作与其余操作一律 403。判定与
// 客户端是否携带 attestation 头无关（header 只属 readback 链路绑定），且对
// public 与 runtime 两种 operation 边界一致生效。

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/runtime/operation"
)

func researchCapabilityDescriptor(
	operationID string,
	method string,
	pathTemplate string,
	kind string,
	commercialStatus string,
) OperationSecurityDescriptor {
	descriptor := OperationSecurityDescriptor{
		CanonicalOperationID: operationID,
		ContractGraphSHA256:  testContractGraphSHA256,
		Method:               method,
		PathTemplate:         pathTemplate,
		OperationKind:        kind,
		AuthMode:             "optional",
		ActorRequirement:     "none",
		Principal:            "public",
		CommercialStatus:     commercialStatus,
	}
	if kind == "command" {
		descriptor.MutationTarget = "TestAggregate"
		descriptor.InvariantTarget = "TestAggregate"
	}
	return descriptor
}

func researchPrincipal() Principal {
	return Principal{
		Actor:  operation.ActorContext{AccountID: "account-research"},
		Claims: Claims{Roles: []string{RoleResearch}},
	}
}

func researchAccountCapabilityDescriptor(
	operationID string,
	method string,
	pathTemplate string,
	kind string,
) OperationSecurityDescriptor {
	descriptor := researchCapabilityDescriptor(
		operationID,
		method,
		pathTemplate,
		kind,
		"blocked",
	)
	descriptor.AuthMode = "required"
	descriptor.ActorRequirement = "account"
	descriptor.Principal = "account"
	return descriptor
}

func TestPublicBoundaryAllowsNamedBlockedOperationsForResearchPrincipal(t *testing.T) {
	t.Parallel()

	for _, testCase := range []struct {
		operationID string
		method      string
		template    string
		path        string
		kind        string
	}{
		{
			operationID: "user.account_session.IssueWhitelistedResearchSession",
			method:      http.MethodPost,
			template:    "/auth/research/session",
			path:        "/auth/research/session",
			kind:        "command",
		},
		{
			operationID: "user.account_session.GetResearchSessionAttestation",
			method:      http.MethodGet,
			template:    "/auth/research/session/attestation",
			path:        "/auth/research/session/attestation",
			kind:        "query",
		},
	} {
		t.Run(testCase.operationID, func(t *testing.T) {
			t.Parallel()
			reached := false
			guard := RequireGeneratedOperationAuthorization(
				[]OperationSecurityDescriptor{researchAccountCapabilityDescriptor(
					testCase.operationID,
					testCase.method,
					testCase.template,
					testCase.kind,
				)},
			)
			handler := guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				reached = true
				w.WriteHeader(http.StatusNoContent)
			}))
			request := httptest.NewRequest(testCase.method, testCase.path, nil)
			request = request.WithContext(
				WithPrincipal(request.Context(), researchPrincipal()),
			)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if !reached || response.Code != http.StatusNoContent {
				t.Fatalf(
					"named research operation denied at public boundary: reached=%t status=%d",
					reached,
					response.Code,
				)
			}
		})
	}
}

func TestPublicBoundaryKeepsBlockedOperationsClosedOutsideResearchCapability(t *testing.T) {
	t.Parallel()

	for _, testCase := range []struct {
		name          string
		descriptor    OperationSecurityDescriptor
		principal     Principal
		withPrincipal bool
	}{
		{
			name: "anonymous caller cannot issue research session",
			descriptor: researchAccountCapabilityDescriptor(
				"user.account_session.IssueWhitelistedResearchSession",
				http.MethodPost,
				"/auth/research/session",
				"command",
			),
		},
		{
			name: "ordinary account cannot issue research session",
			descriptor: researchAccountCapabilityDescriptor(
				"user.account_session.IssueWhitelistedResearchSession",
				http.MethodPost,
				"/auth/research/session",
				"command",
			),
			principal: Principal{
				Actor: operation.ActorContext{AccountID: "account-ordinary"},
			},
			withPrincipal: true,
		},
		{
			name: "research account cannot reach unnamed blocked query",
			descriptor: researchAccountCapabilityDescriptor(
				"content.post.GetHelperRead",
				http.MethodGet,
				"/content/helper-read",
				"query",
			),
			principal:     researchPrincipal(),
			withPrincipal: true,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()
			handler := RequireGeneratedOperationAuthorization(
				[]OperationSecurityDescriptor{testCase.descriptor},
			)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
				t.Fatal("blocked operation reached handler outside research capability")
			}))
			request := httptest.NewRequest(
				testCase.descriptor.Method,
				testCase.descriptor.PathTemplate,
				nil,
			)
			if testCase.withPrincipal {
				request = request.WithContext(
					WithPrincipal(request.Context(), testCase.principal),
				)
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusForbidden {
				t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
			}
		})
	}
}

func TestResearchRoleDeniedOutsideCapabilitySurface(t *testing.T) {
	t.Parallel()

	for _, testCase := range []struct {
		name             string
		operationID      string
		method           string
		template         string
		path             string
		kind             string
		commercialStatus string
	}{
		{
			name:             "write command is denied",
			operationID:      "content.outbound_share_fact.AppendOutboundShareFact",
			method:           http.MethodPost,
			template:         "/content/posts/{postId}/outbound-shares",
			path:             "/content/posts/p1/outbound-shares",
			kind:             "command",
			commercialStatus: "ready",
		},
		{
			name:             "blocked unnamed query is denied",
			operationID:      "content.post.GetHelperRead",
			method:           http.MethodGet,
			template:         "/content/helper-read",
			path:             "/content/helper-read",
			kind:             "query",
			commercialStatus: "blocked",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()
			guard := researchRuntimeBoundaryGuard(
				t,
				[]OperationSecurityDescriptor{researchCapabilityDescriptor(
					testCase.operationID,
					testCase.method,
					testCase.template,
					testCase.kind,
					testCase.commercialStatus,
				)},
			)
			handler := guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
				t.Fatal("research principal reached handler outside capability surface")
			}))
			request := httptest.NewRequest(testCase.method, testCase.path, nil)
			request = request.WithContext(
				WithPrincipal(request.Context(), researchPrincipal()),
			)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusForbidden {
				t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
			}
		})
	}
}

// researchRuntimeBoundaryGuard 以 runtime 边界装配 guard：研究收敛必须与部署
// 边界无关，runtime 边界会放行 blocked 操作，正是需要 role 收敛兜底的一侧。
func researchRuntimeBoundaryGuard(
	t *testing.T,
	descriptors []OperationSecurityDescriptor,
) func(http.Handler) http.Handler {
	t.Helper()
	guard, err := RequireGeneratedOperationAuthorizationForTestLive(
		descriptors,
		validMutableTestLiveOperationIdentity("gamma"),
	)
	if err != nil {
		t.Fatalf("test-live guard composition failed: %v", err)
	}
	return guard
}

func TestResearchRoleAllowsCapabilitySurfaceOperations(t *testing.T) {
	t.Parallel()

	for _, testCase := range []struct {
		operationID      string
		method           string
		template         string
		path             string
		kind             string
		commercialStatus string
	}{
		{
			operationID:      "content.post.GetFeed",
			method:           http.MethodGet,
			template:         "/content/feed",
			path:             "/content/feed",
			kind:             "query",
			commercialStatus: "ready",
		},
		{
			operationID:      "content.post.GetPost",
			method:           http.MethodGet,
			template:         "/content/posts/{postId}",
			path:             "/content/posts/p1",
			kind:             "query",
			commercialStatus: "ready",
		},
		{
			operationID:      "entity.homepage.GetHomepageIntroduction",
			method:           http.MethodGet,
			template:         "/entity/homepages/{homepageId}/introduction",
			path:             "/entity/homepages/h1/introduction",
			kind:             "query",
			commercialStatus: "ready",
		},
		{
			operationID:      "user.account_session.GetResearchSessionAttestation",
			method:           http.MethodGet,
			template:         "/auth/research/session/attestation",
			path:             "/auth/research/session/attestation",
			kind:             "query",
			commercialStatus: "blocked",
		},
		{
			operationID:      "content.post.GetResearchReleaseReadback",
			method:           http.MethodGet,
			template:         "/content/research/readback",
			path:             "/content/research/readback",
			kind:             "query",
			commercialStatus: "blocked",
		},
		{
			operationID:      "content.original_access_quota.ReserveOriginalImageAccessGrant",
			method:           http.MethodPost,
			template:         "/content/media/{mediaId}/original:access",
			path:             "/content/media/m1/original:access",
			kind:             "command",
			commercialStatus: "ready",
		},
		{
			operationID:      "content.original_access_quota.GetOriginalImageAccessAudit",
			method:           http.MethodGet,
			template:         "/content/media/original-access-audits/{auditId}",
			path:             "/content/media/original-access-audits/a1",
			kind:             "query",
			commercialStatus: "ready",
		},
	} {
		t.Run(testCase.operationID, func(t *testing.T) {
			t.Parallel()
			reached := false
			guard := researchRuntimeBoundaryGuard(
				t,
				[]OperationSecurityDescriptor{researchCapabilityDescriptor(
					testCase.operationID,
					testCase.method,
					testCase.template,
					testCase.kind,
					testCase.commercialStatus,
				)},
			)
			handler := guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
				reached = true
			}))
			request := httptest.NewRequest(testCase.method, testCase.path, nil)
			request = request.WithContext(
				WithPrincipal(request.Context(), researchPrincipal()),
			)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if !reached {
				t.Fatalf(
					"capability-surface operation was denied: status=%d",
					response.Code,
				)
			}
		})
	}
}

func TestNonResearchPrincipalIsNotAffectedByResearchCapabilitySurface(t *testing.T) {
	t.Parallel()

	reached := false
	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{researchCapabilityDescriptor(
			"content.outbound_share_fact.AppendOutboundShareFact",
			http.MethodPost,
			"/content/posts/{postId}/outbound-shares",
			"command",
			"ready",
		)},
	)
	handler := guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		reached = true
	}))
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/p1/outbound-shares",
		nil,
	)
	request = request.WithContext(WithPrincipal(request.Context(), Principal{
		Actor: operation.ActorContext{AccountID: "account-normal"},
	}))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if !reached {
		t.Fatalf("non-research principal must pass research surface: status=%d", response.Code)
	}
}

func TestAttestationHeaderAloneDoesNotChangeCapabilitySurface(t *testing.T) {
	t.Parallel()

	// DEC-032：header 是 readback 链路绑定，不是能力面判定依据。携带 header
	// 而无 research role 的请求不被收敛；反之亦然（role 收敛见上组用例）。
	reached := false
	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{researchCapabilityDescriptor(
			"content.outbound_share_fact.AppendOutboundShareFact",
			http.MethodPost,
			"/content/posts/{postId}/outbound-shares",
			"command",
			"ready",
		)},
	)
	handler := guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		reached = true
	}))
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/p1/outbound-shares",
		nil,
	)
	request.Header.Set(ResearchAttestationHeader, "attested-token")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if !reached {
		t.Fatalf("attestation header alone must not deny: status=%d", response.Code)
	}
}
