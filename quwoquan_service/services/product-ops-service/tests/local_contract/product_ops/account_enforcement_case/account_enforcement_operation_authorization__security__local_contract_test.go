package local_contract

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

type expectedAccountEnforcementAuthorization struct {
	scope            string
	commercialStatus string
}

var expectedAccountEnforcementAuthorizations = map[string]expectedAccountEnforcementAuthorization{
	"ops.account_enforcement_case.GetAccountEnforcementCase": {
		scope:            "ops.account.enforcement.read",
		commercialStatus: "blocked",
	},
	"ops.account_enforcement_case.OpenAccountAppealCase": {
		scope:            "ops.account.appeal.write",
		commercialStatus: "blocked",
	},
	"ops.account_enforcement_case.OpenAccountModerationCase": {
		scope:            "ops.account.moderation.write",
		commercialStatus: "blocked",
	},
	"ops.account_enforcement_case.RetryAccountEnforcementDelivery": {
		scope:            "ops.account.enforcement.recover",
		commercialStatus: "blocked",
	},
	"ops.account_enforcement_case.ReviewAccountEnforcementCase": {
		scope:            "ops.account.enforcement.review",
		commercialStatus: "blocked",
	},
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-003
func TestAccountEnforcementUsesOneGeneratedScopeTableAtProductOpsBoundary(
	t *testing.T,
) {
	descriptors := accountEnforcementOperationDescriptors(t)
	if len(descriptors) != len(expectedAccountEnforcementAuthorizations) {
		t.Fatalf(
			"account enforcement generated operation count=%d want=%d",
			len(descriptors),
			len(expectedAccountEnforcementAuthorizations),
		)
	}
	for _, descriptor := range descriptors {
		expected, ok := expectedAccountEnforcementAuthorizations[descriptor.CanonicalOperationID]
		if !ok {
			t.Fatalf(
				"unexpected account enforcement operation %q",
				descriptor.CanonicalOperationID,
			)
		}
		if descriptor.CommercialStatus != expected.commercialStatus {
			t.Fatalf(
				"%s commercial status=%q want=%q",
				descriptor.CanonicalOperationID,
				descriptor.CommercialStatus,
				expected.commercialStatus,
			)
		}
		if descriptor.AuthMode != "required" ||
			descriptor.ActorRequirement != "account" ||
			descriptor.Principal != "operator" ||
			len(descriptor.Scopes) != 1 ||
			descriptor.Scopes[0] != expected.scope {
			t.Fatalf(
				"%s authorization=%s/%s/%s scopes=%v want required/account/operator/%s",
				descriptor.CanonicalOperationID,
				descriptor.AuthMode,
				descriptor.ActorRequirement,
				descriptor.Principal,
				descriptor.Scopes,
				expected.scope,
			)
		}
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-003
func TestAccountEnforcementOuterGeneratedGuardFailsClosedByScopeAndStatus(
	t *testing.T,
) {
	descriptors := accountEnforcementOperationDescriptors(t)
	guard := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("ops"),
	)
	for _, descriptor := range descriptors {
		descriptor := descriptor
		t.Run(descriptor.CanonicalOperationID, func(t *testing.T) {
			expected := expectedAccountEnforcementAuthorizations[descriptor.CanonicalOperationID]
			exactStatus := http.StatusNoContent
			exactCalls := 1
			if expected.commercialStatus == "blocked" {
				exactStatus = http.StatusForbidden
				exactCalls = 0
			}
			for _, test := range []struct {
				name       string
				scope      string
				roles      []string
				wantStatus int
				wantCalls  int
			}{
				{
					name:       "missing_scope",
					roles:      []string{"operator"},
					wantStatus: http.StatusForbidden,
				},
				{
					name:       "wrong_scope",
					scope:      "ops.account.enforcement.unrelated",
					roles:      []string{"operator"},
					wantStatus: http.StatusForbidden,
				},
				{
					name:       "wrong_principal_with_exact_scope",
					scope:      expected.scope,
					roles:      []string{"account"},
					wantStatus: http.StatusForbidden,
				},
				{
					name:       "exact_generated_scope",
					scope:      expected.scope,
					roles:      []string{"operator"},
					wantStatus: exactStatus,
					wantCalls:  exactCalls,
				},
			} {
				test := test
				t.Run(test.name, func(t *testing.T) {
					ownerCalls := 0
					handler := guard(http.HandlerFunc(func(
						response http.ResponseWriter,
						request *http.Request,
					) {
						ownerCalls++
						current, ok := rtauth.OperationDescriptorFromContext(
							request.Context(),
						)
						if !ok ||
							current.CanonicalOperationID !=
								descriptor.CanonicalOperationID {
							t.Fatalf(
								"generated operation context=%+v ok=%t",
								current,
								ok,
							)
						}
						response.WriteHeader(http.StatusNoContent)
					}))
					request := httptest.NewRequest(
						descriptor.Method,
						concreteOperationPath(descriptor.PathTemplate),
						nil,
					)
					if descriptor.Idempotency == "required" {
						request.Header.Set(
							"Idempotency-Key",
							"scope-boundary-"+test.name,
						)
					}
					request = request.WithContext(rtauth.WithPrincipal(
						request.Context(),
						rtauth.Principal{
							Claims: rtauth.Claims{
								Roles: test.roles,
								Scope: test.scope,
							},
							Actor: operation.ActorContext{
								AccountID: "operator-scope-test",
							},
						},
					))
					response := httptest.NewRecorder()
					handler.ServeHTTP(response, request)
					if response.Code != test.wantStatus ||
						ownerCalls != test.wantCalls {
						t.Fatalf(
							"status=%d calls=%d want=%d/%d body=%s",
							response.Code,
							ownerCalls,
							test.wantStatus,
							test.wantCalls,
							response.Body.String(),
						)
					}
				})
			}
		})
	}
}

func accountEnforcementOperationDescriptors(
	t *testing.T,
) []rtauth.OperationSecurityDescriptor {
	t.Helper()
	const operationPrefix = "ops.account_enforcement_case."
	descriptors := make([]rtauth.OperationSecurityDescriptor, 0, 5)
	for _, descriptor := range operationsecurity.ForDomain("ops") {
		if strings.HasPrefix(descriptor.CanonicalOperationID, operationPrefix) {
			descriptors = append(descriptors, descriptor)
		}
	}
	return descriptors
}

func concreteOperationPath(pathTemplate string) string {
	return strings.ReplaceAll(pathTemplate, "{caseId}", "case-scope-test")
}
