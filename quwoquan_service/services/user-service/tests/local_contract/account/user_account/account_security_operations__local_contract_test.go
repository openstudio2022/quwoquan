// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
// readiness_case: read-account-security-local
// readiness_case: check-account-security-authority-local
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	userhttp "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

type readinessAccountSecurityReader struct {
	requested []string
}

func (reader *readinessAccountSecurityReader) ReadAccountSecurity(
	_ context.Context,
	accountID string,
) (accountports.AccountSecuritySnapshot, error) {
	reader.requested = append(reader.requested, accountID)
	if accountID == "__account_security_authority_readiness_probe__" {
		return accountports.AccountSecuritySnapshot{}, accountports.ErrAccountNotFound
	}
	return accountports.AccountSecuritySnapshot{
		AccountState: "active",
		AuthEpoch:    7,
	}, nil
}

func readinessServiceRequest(path string) *http.Request {
	request := httptest.NewRequest(http.MethodGet, path, nil)
	principal := rtauth.Principal{
		Claims: rtauth.Claims{
			Roles: []string{"service"},
			Scope: "user.account.security.read",
		},
		Actor: operation.ActorContext{AccountID: "service:content-service"},
	}
	return request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
}

func TestAccountSecurityOperationsInvokeTheAuthorityReader(t *testing.T) {
	reader := &readinessAccountSecurityReader{}
	handler := (&userhttp.UserHandler{}).WithAccountSecurityReader(reader)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	readResponse := httptest.NewRecorder()
	mux.ServeHTTP(
		readResponse,
		readinessServiceRequest("/internal/user/accounts/account-readiness/security"),
	)
	if readResponse.Code != http.StatusOK {
		t.Fatalf("ReadAccountSecurity status=%d body=%s", readResponse.Code, readResponse.Body.String())
	}
	var snapshot map[string]any
	if err := json.Unmarshal(readResponse.Body.Bytes(), &snapshot); err != nil {
		t.Fatalf("decode ReadAccountSecurity response: %v", err)
	}
	if snapshot["accountState"] != "active" || snapshot["authEpoch"] != float64(7) {
		t.Fatalf("ReadAccountSecurity snapshot=%#v", snapshot)
	}

	healthResponse := httptest.NewRecorder()
	mux.ServeHTTP(
		healthResponse,
		readinessServiceRequest("/internal/user/account-security/health"),
	)
	if healthResponse.Code != http.StatusOK || healthResponse.Body.String() != "{\"status\":\"ok\"}\n" {
		t.Fatalf("CheckAccountSecurityAuthority status=%d body=%s", healthResponse.Code, healthResponse.Body.String())
	}

	want := []string{"account-readiness", "__account_security_authority_readiness_probe__"}
	if len(reader.requested) != len(want) {
		t.Fatalf("authority reader calls=%v want=%v", reader.requested, want)
	}
	for index := range want {
		if reader.requested[index] != want[index] {
			t.Fatalf("authority reader calls=%v want=%v", reader.requested, want)
		}
	}
}
