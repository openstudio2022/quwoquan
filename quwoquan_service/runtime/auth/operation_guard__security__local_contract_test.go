package auth

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
)

const testContractGraphSHA256 = "test-contract-graph-sha256"

func TestGeneratedOperationGuardDefaultsUnknownAndBlockedRoutesToDeny(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{{
			CanonicalOperationID: "content.report.CreateReport",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodPost,
			PathTemplate:         "/api/v1/content/reports",
			OperationKind:        "command",
			MutationTarget:       "Report",
			InvariantTarget:      "Report",
			AuthMode:             "required",
			ActorRequirement:     "persona",
			Principal:            "persona",
			CommercialStatus:     "blocked",
		}},
	)
	handler := guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("blocked request reached handler")
	}))

	for _, testCase := range []struct {
		name       string
		path       string
		wantStatus int
	}{
		{name: "unknown", path: "/api/v1/content/unknown", wantStatus: http.StatusNotFound},
		{name: "blocked", path: "/api/v1/content/reports", wantStatus: http.StatusForbidden},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodPost, testCase.path, nil)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != testCase.wantStatus {
				t.Fatalf("status = %d, want %d", response.Code, testCase.wantStatus)
			}
		})
	}
}

func TestGeneratedOperationGuardPropagatesMetadataDeadline(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{{
			CanonicalOperationID: "content.report.CreateReport",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodPost,
			PathTemplate:         "/v1/content/reports",
			OperationKind:        "command",
			MutationTarget:       "Report",
			InvariantTarget:      "Report",
			AuthMode:             "public",
			ActorRequirement:     "none",
			CommercialStatus:     "ready",
			TimeoutMilliseconds:  1,
		}},
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-r.Context().Done():
			if !errors.Is(r.Context().Err(), context.DeadlineExceeded) {
				t.Fatalf("operation context error=%v want deadline exceeded", r.Context().Err())
			}
			w.WriteHeader(http.StatusNoContent)
		case <-time.After(time.Second):
			t.Fatal("generated operation deadline was not propagated")
		}
	}))

	response := httptest.NewRecorder()
	handler.ServeHTTP(
		response,
		httptest.NewRequest(http.MethodPost, "/v1/content/reports", nil),
	)
	if response.Code != http.StatusNoContent {
		t.Fatalf("status=%d want=%d", response.Code, http.StatusNoContent)
	}
}

func TestGeneratedOperationGuardRequiresVerifiedActorAndScopes(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{{
			CanonicalOperationID: "content.report.CreateReport",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodPost,
			PathTemplate:         "/api/v1/content/reports/{reportId}",
			OperationKind:        "command",
			MutationTarget:       "Report",
			InvariantTarget:      "Report",
			AuthMode:             "required",
			ActorRequirement:     "persona",
			Principal:            "persona",
			Scopes:               []string{"content.report.write"},
			CommercialStatus:     "ready",
		}},
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		descriptor, ok := OperationDescriptorFromContext(r.Context())
		if !ok ||
			descriptor.CanonicalOperationID != "content.report.CreateReport" ||
			descriptor.ContractGraphSHA256 != testContractGraphSHA256 {
			t.Fatal("generated operation descriptor missing from context")
		}
		current, ok := operation.FromContext(r.Context())
		if !ok ||
			current.OperationID != descriptor.CanonicalOperationID ||
			current.Actor.PersonaID != "persona-1" ||
			current.IdempotencyKey != "idempotency-1" {
			t.Fatalf("trusted operation context missing: %+v ok=%v", current, ok)
		}
		w.WriteHeader(http.StatusNoContent)
	}))

	for _, testCase := range []struct {
		name       string
		principal  *Principal
		wantStatus int
	}{
		{name: "missing principal", wantStatus: http.StatusUnauthorized},
		{
			name:       "missing persona",
			principal:  &Principal{Actor: operation.ActorContext{AccountID: "account-1"}, Claims: Claims{Scope: "content.report.write"}},
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "missing scope",
			principal:  &Principal{Actor: operation.ActorContext{AccountID: "account-1", PersonaID: "persona-1"}},
			wantStatus: http.StatusForbidden,
		},
		{
			name: "authorized",
			principal: &Principal{
				Claims: Claims{Scope: "content.report.write"},
				Actor: operation.ActorContext{
					AccountID: "account-1",
					PersonaID: "persona-1",
				},
			},
			wantStatus: http.StatusNoContent,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/api/v1/content/reports/report-1",
				nil,
			)
			request.Header.Set("Idempotency-Key", "idempotency-1")
			if testCase.principal != nil {
				request = request.WithContext(
					WithPrincipal(request.Context(), *testCase.principal),
				)
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != testCase.wantStatus {
				t.Fatalf("status = %d, want %d", response.Code, testCase.wantStatus)
			}
		})
	}
}

func TestGeneratedOperationGuardOptionalActorStillFailsClosed(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{{
			CanonicalOperationID: "integration.location.GetNearbyLocations",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodGet,
			PathTemplate:         "/api/v1/locations/nearby",
			OperationKind:        "query",
			AuthMode:             "optional",
			ActorRequirement:     "persona_or_device",
			Principal:            "public",
			CommercialStatus:     "ready",
		}},
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/locations/nearby",
		nil,
	)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func TestGeneratedOperationGuardForRouteUsesOnlyTheGeneratedDescriptor(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorizationForRoute(
		[]OperationSecurityDescriptor{
			{
				CanonicalOperationID: "user.user_profile.PullUserSync",
				ContractGraphSHA256:  testContractGraphSHA256,
				Method:               http.MethodPost,
				PathTemplate:         "/v1/user/sync",
				OperationKind:        "command",
				MutationTarget:       "UserAccount",
				InvariantTarget:      "UserAccount",
				AuthMode:             "required",
				ActorRequirement:     "account",
				Principal:            "account",
				CommercialStatus:     "ready",
			},
			{
				CanonicalOperationID: "user.user_profile.GetProfile",
				ContractGraphSHA256:  testContractGraphSHA256,
				Method:               http.MethodGet,
				PathTemplate:         "/v1/user/profile/{userId}",
				OperationKind:        "query",
				AuthMode:             "public",
				ActorRequirement:     "none",
				Principal:            "public",
				CommercialStatus:     "ready",
			},
		},
		http.MethodPost,
		"/v1/user/sync",
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))

	unauthenticated := httptest.NewRequest(http.MethodPost, "/v1/user/sync", nil)
	unauthenticatedRecorder := httptest.NewRecorder()
	handler.ServeHTTP(unauthenticatedRecorder, unauthenticated)
	if unauthenticatedRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("unauthenticated status=%d want=%d", unauthenticatedRecorder.Code, http.StatusUnauthorized)
	}

	authorized := httptest.NewRequest(http.MethodPost, "/v1/user/sync", nil)
	authorized = authorized.WithContext(WithPrincipal(authorized.Context(), Principal{
		Actor: operation.ActorContext{AccountID: "account-1"},
	}))
	authorizedRecorder := httptest.NewRecorder()
	handler.ServeHTTP(authorizedRecorder, authorized)
	if authorizedRecorder.Code != http.StatusNoContent {
		t.Fatalf("authorized status=%d want=%d", authorizedRecorder.Code, http.StatusNoContent)
	}
}

func TestGeneratedOperationGuardForRouteAllowsReadyAnonymousBootstrap(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorizationForRoute(
		[]OperationSecurityDescriptor{{
			CanonicalOperationID: "user.user_profile.LoginAnonymous",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodPost,
			PathTemplate:         "/v1/auth/login/anonymous",
			OperationKind:        "command",
			MutationTarget:       "AuthenticationChallenge",
			InvariantTarget:      "AuthenticationChallenge",
			AuthMode:             "public",
			ActorRequirement:     "none",
			Principal:            "public",
			CommercialStatus:     "ready",
		}},
		http.MethodPost,
		"/v1/auth/login/anonymous",
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))

	response := httptest.NewRecorder()
	handler.ServeHTTP(
		response,
		httptest.NewRequest(http.MethodPost, "/v1/auth/login/anonymous", nil),
	)
	if response.Code != http.StatusNoContent {
		t.Fatalf("anonymous bootstrap status=%d want=%d", response.Code, http.StatusNoContent)
	}
}

func TestGeneratedOperationGuardSeparatesScopesPermissionsAndRoles(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{{
			CanonicalOperationID: "ops.audit.Read",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodGet,
			PathTemplate:         "/v1/ops/audit/{auditId}",
			OperationKind:        "query",
			AuthMode:             "required",
			ActorRequirement:     "account",
			Principal:            "operator",
			Scopes:               []string{"ops.read"},
			Permissions:          []string{"audit.inspect"},
			CommercialStatus:     "ready",
		}},
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	for _, testCase := range []struct {
		name       string
		principal  Principal
		wantStatus int
	}{
		{
			name: "permission cannot be smuggled through scope",
			principal: Principal{
				Claims: Claims{
					Scope: "ops.read audit.inspect",
					Roles: []string{"operator"},
				},
				Actor: operation.ActorContext{AccountID: "account-1"},
			},
			wantStatus: http.StatusForbidden,
		},
		{
			name: "role cannot be smuggled through scope",
			principal: Principal{
				Claims: Claims{
					Scope:       "ops.read operator",
					Permissions: []string{"audit.inspect"},
				},
				Actor: operation.ActorContext{AccountID: "account-1"},
			},
			wantStatus: http.StatusForbidden,
		},
		{
			name: "authorized",
			principal: Principal{
				Claims: Claims{
					Scope:       "ops.read",
					Permissions: []string{"audit.inspect"},
					Roles:       []string{"operator"},
				},
				Actor: operation.ActorContext{AccountID: "account-1"},
			},
			wantStatus: http.StatusNoContent,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, "/v1/ops/audit/audit-1", nil)
			request = request.WithContext(
				WithPrincipal(request.Context(), testCase.principal),
			)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != testCase.wantStatus {
				t.Fatalf("status=%d, want=%d", response.Code, testCase.wantStatus)
			}
		})
	}
}

func TestGeneratedOperationEnforcerFailsClosedForBlockedObjects(t *testing.T) {
	t.Parallel()

	ownerCalls := 0
	handler := EnforceGeneratedOperationAuthorization([]OperationSecurityDescriptor{
		{
			CanonicalOperationID: "integration.location.SearchLocations",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodGet,
			PathTemplate:         "/v1/integration/location/search",
			OperationKind:        "query",
			AuthMode:             "optional",
			ActorRequirement:     "none",
			Principal:            "public",
			CommercialStatus:     "ready",
		},
		{
			CanonicalOperationID: "integration.external.Submit",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodPost,
			PathTemplate:         "/v1/integration/external",
			OperationKind:        "command",
			MutationTarget:       "ExternalInteraction",
			InvariantTarget:      "ExternalInteraction",
			AuthMode:             "deny",
			CommercialStatus:     "blocked",
		},
	})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		ownerCalls++
		w.WriteHeader(http.StatusNoContent)
	}))

	readyRequest := httptest.NewRequest(
		http.MethodGet,
		"/v1/integration/location/search",
		nil,
	)
	readyResponse := httptest.NewRecorder()
	handler.ServeHTTP(readyResponse, readyRequest)
	if readyResponse.Code != http.StatusNoContent {
		t.Fatalf("ready status=%d", readyResponse.Code)
	}
	blockedRequest := httptest.NewRequest(
		http.MethodPost,
		"/v1/integration/external",
		nil,
	)
	blockedResponse := httptest.NewRecorder()
	handler.ServeHTTP(blockedResponse, blockedRequest)
	if blockedResponse.Code != http.StatusForbidden || ownerCalls != 1 {
		t.Fatalf(
			"blocked generated operation must not reach owner: status=%d calls=%d",
			blockedResponse.Code,
			ownerCalls,
		)
	}
}

func TestGeneratedOperationGuardPanicsOnMalformedOrDuplicateRoute(t *testing.T) {
	t.Parallel()

	for _, descriptors := range [][]OperationSecurityDescriptor{
		{},
		{{
			CanonicalOperationID: "missing.graph.hash",
			Method:               http.MethodGet,
			PathTemplate:         "/v1/missing-graph-hash",
			OperationKind:        "query",
		}},
		{{
			CanonicalOperationID: "bad.path",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodGet,
			PathTemplate:         "/v1/{bad/path}",
			OperationKind:        "query",
		}},
		{{
			CanonicalOperationID: "missing.operation.kind",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodGet,
			PathTemplate:         "/v1/missing-operation-kind",
		}},
		{{
			CanonicalOperationID: "missing.command.targets",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodPost,
			PathTemplate:         "/v1/missing-command-targets",
			OperationKind:        "command",
		}},
		{{
			CanonicalOperationID: "mismatched.command.targets",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodPost,
			PathTemplate:         "/v1/mismatched-command-targets",
			OperationKind:        "command",
			MutationTarget:       "FirstAggregate",
			InvariantTarget:      "SecondAggregate",
		}},
		{
			{
				CanonicalOperationID: "duplicate.a",
				ContractGraphSHA256:  testContractGraphSHA256,
				Method:               http.MethodGet,
				PathTemplate:         "/v1/items/{itemId}",
				OperationKind:        "query",
			},
			{
				CanonicalOperationID: "duplicate.b",
				ContractGraphSHA256:  testContractGraphSHA256,
				Method:               http.MethodGet,
				PathTemplate:         "/v1/items/{otherId}",
				OperationKind:        "query",
			},
		},
		{
			{
				CanonicalOperationID: "mixed.graph.a",
				ContractGraphSHA256:  testContractGraphSHA256,
				Method:               http.MethodGet,
				PathTemplate:         "/v1/mixed-graph/a",
				OperationKind:        "query",
			},
			{
				CanonicalOperationID: "mixed.graph.b",
				ContractGraphSHA256:  "different-contract-graph-sha256",
				Method:               http.MethodGet,
				PathTemplate:         "/v1/mixed-graph/b",
				OperationKind:        "query",
			},
		},
	} {
		func() {
			defer func() {
				if recover() == nil {
					t.Fatal("invalid generated route must panic at composition")
				}
			}()
			RequireGeneratedOperationAuthorization(descriptors)
		}()
	}
}

func TestGeneratedOperationGuardSelectsMostSpecificMatchingRoute(t *testing.T) {
	t.Parallel()

	handler := RequireGeneratedOperationAuthorization([]OperationSecurityDescriptor{
		{
			CanonicalOperationID: "content.media_asset.GetOwnedMediaAsset",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodGet,
			PathTemplate:         "/internal/v1/content/media/{mediaId}",
			OperationKind:        "query",
			AuthMode:             "public",
			ActorRequirement:     "none",
			Principal:            "public",
			CommercialStatus:     "ready",
		},
		{
			CanonicalOperationID: "content.media_asset.GetMediaAssetReference",
			ContractGraphSHA256:  testContractGraphSHA256,
			Method:               http.MethodGet,
			PathTemplate:         "/internal/v1/content/media/{mediaId}:reference",
			OperationKind:        "query",
			AuthMode:             "public",
			ActorRequirement:     "none",
			Principal:            "public",
			CommercialStatus:     "ready",
		},
	})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		descriptor, ok := OperationDescriptorFromContext(r.Context())
		if !ok || descriptor.CanonicalOperationID != "content.media_asset.GetMediaAssetReference" {
			t.Fatalf("specific route was not selected: %#v ok=%v", descriptor, ok)
		}
		w.WriteHeader(http.StatusNoContent)
	}))

	request := httptest.NewRequest(http.MethodGet, "/internal/v1/content/media/asset-1:reference", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("specific route status=%d body=%s", response.Code, response.Body.String())
	}
}
