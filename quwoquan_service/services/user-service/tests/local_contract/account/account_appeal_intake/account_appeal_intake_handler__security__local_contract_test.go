// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
// readiness_case: claim-account-appeal-intake-local
package local_contract

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	appealhttp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/adapters/inbound/http"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
func TestClaimAppealIntakeRequiresGeneratedOperationAndProductOpsPrincipal(t *testing.T) {
	tests := []struct {
		name       string
		principal  string
		wantStatus int
		wantClaims int
	}{
		{name: "missing trusted context", wantStatus: http.StatusUnauthorized},
		{
			name:      "another service is forbidden",
			principal: "service:another-service", wantStatus: http.StatusForbidden,
		},
		{
			name:      "product ops exact claim",
			principal: "service:product-ops-service", wantStatus: http.StatusOK,
			wantClaims: 1,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store := &appealStoreProbe{}
			facade := application.NewCommandFacade(store, &identityProbe{}, nil)
			handler, err := appealhttp.NewHandler(facade)
			if err != nil {
				t.Fatal(err)
			}
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)
			request := httptest.NewRequest(
				http.MethodPost,
				"/internal/user/account-appeal-intakes/"+testAppealIntakeRef+":claim",
				bytes.NewBufferString(`{"accountId":"`+testAppealAccountID+`","caseId":"appeal-1"}`),
			)
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("Idempotency-Key", "claim-1")
			requestContext := request.Context()
			if test.principal != "" {
				requestContext = rtauth.WithPrincipal(requestContext, rtauth.Principal{
					Claims: rtauth.Claims{
						Scope: "user.account.appeal_intake.claim", Roles: []string{"service"},
					},
					Actor: operation.ActorContext{AccountID: test.principal},
				})
			}
			request = request.WithContext(requestContext)
			response := httptest.NewRecorder()
			boundary := http.Handler(mux)
			if test.principal != "" {
				boundary = rtauth.RequireGeneratedOperationAuthorizationForRoute(
					operationsecurity.ForDomain("user"), http.MethodPost, appealhttp.ClaimIntakePath,
				)(boundary)
			}
			boundary.ServeHTTP(response, request)

			if response.Code != test.wantStatus {
				t.Fatalf("status=%d want=%d body=%s", response.Code, test.wantStatus, response.Body.String())
			}
			if len(store.claimed) != test.wantClaims {
				t.Fatalf("claim calls=%d want=%d", len(store.claimed), test.wantClaims)
			}
			if test.wantClaims == 1 {
				claim := store.claimed[0]
				if claim.IntakeRef != testAppealIntakeRef || claim.AccountID != testAppealAccountID ||
					claim.CaseID != "appeal-1" || claim.IdempotencyKey != "claim-1" {
					t.Fatalf("claim tuple=%+v", claim)
				}
			}
		})
	}
}
