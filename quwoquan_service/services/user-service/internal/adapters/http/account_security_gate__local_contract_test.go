package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
)

type staticAccountSecurityReader struct {
	snapshot accountports.AccountSecuritySnapshot
	err      error
	calls    int
}

func (reader *staticAccountSecurityReader) ReadAccountSecurity(
	context.Context,
	string,
) (accountports.AccountSecuritySnapshot, error) {
	reader.calls++
	return reader.snapshot, reader.err
}

func TestAccountSecurityGateRejectsSuspendedAccount(t *testing.T) {
	reader := &staticAccountSecurityReader{
		snapshot: accountports.AccountSecuritySnapshot{
			AccountState: "suspended",
			AuthEpoch:    2,
		},
	}
	handler := (&UserHandler{accountSecurity: reader}).enforceAccountSecurity(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	response := executeAccountSecurityRequest(
		t,
		handler,
		rtauth.Principal{
			Claims: rtauth.Claims{AuthEpoch: 2},
			Actor:  operation.ActorContext{AccountID: "account-1"},
		},
	)
	if response.Code != http.StatusForbidden || reader.calls != 1 {
		t.Fatalf("suspended account must be rejected before handler: code=%d calls=%d", response.Code, reader.calls)
	}
}

func TestAccountSecurityGateRejectsStaleEpoch(t *testing.T) {
	reader := &staticAccountSecurityReader{
		snapshot: accountports.AccountSecuritySnapshot{
			AccountState: "active",
			AuthEpoch:    3,
		},
	}
	handler := (&UserHandler{accountSecurity: reader}).enforceAccountSecurity(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	response := executeAccountSecurityRequest(
		t,
		handler,
		rtauth.Principal{
			Claims: rtauth.Claims{AuthEpoch: 2},
			Actor:  operation.ActorContext{AccountID: "account-1"},
		},
	)
	if response.Code != http.StatusUnauthorized || reader.calls != 1 {
		t.Fatalf("stale epoch must be rejected before handler: code=%d calls=%d", response.Code, reader.calls)
	}
}

func TestAccountSecurityGateAllowsClosedAccountCloseReplay(t *testing.T) {
	reader := &staticAccountSecurityReader{
		snapshot: accountports.AccountSecuritySnapshot{
			AccountState: "closed",
			AuthEpoch:    2,
		},
	}
	handler := (&UserHandler{accountSecurity: reader}).enforceAccountSecurity(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	response := executeAccountSecurityRequestForOperation(
		t,
		handler,
		rtauth.Principal{
			Claims: rtauth.Claims{AuthEpoch: 1},
			Actor:  operation.ActorContext{AccountID: "account-1"},
		},
		closeAccountOperationID,
	)
	if response.Code != http.StatusNoContent || reader.calls != 1 {
		t.Fatalf(
			"closed account CloseAccount replay must reach idempotent handler: code=%d calls=%d",
			response.Code,
			reader.calls,
		)
	}
}

func TestAccountSecurityGateRejectsClosedAccountOtherOperation(t *testing.T) {
	reader := &staticAccountSecurityReader{
		snapshot: accountports.AccountSecuritySnapshot{
			AccountState: "closed",
			AuthEpoch:    2,
		},
	}
	handler := (&UserHandler{accountSecurity: reader}).enforceAccountSecurity(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	response := executeAccountSecurityRequestForOperation(
		t,
		handler,
		rtauth.Principal{
			Claims: rtauth.Claims{AuthEpoch: 2},
			Actor:  operation.ActorContext{AccountID: "account-1"},
		},
		"user.user_profile.GetUserProfile",
	)
	if response.Code != http.StatusGone || reader.calls != 1 {
		t.Fatalf(
			"closed account non-close operation must be rejected: code=%d calls=%d",
			response.Code,
			reader.calls,
		)
	}
}

func TestAccountSecurityGateFailsClosedWhenReaderUnavailable(t *testing.T) {
	reader := &staticAccountSecurityReader{err: errors.New("postgres unavailable")}
	handler := (&UserHandler{accountSecurity: reader}).enforceAccountSecurity(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	response := executeAccountSecurityRequest(
		t,
		handler,
		rtauth.Principal{
			Claims: rtauth.Claims{AuthEpoch: 1},
			Actor:  operation.ActorContext{AccountID: "account-1"},
		},
	)
	if response.Code != http.StatusInternalServerError || reader.calls != 1 {
		t.Fatalf("reader failure must fail closed: code=%d calls=%d", response.Code, reader.calls)
	}
}

func TestAccountSecurityGateLeavesServicePrincipalToOperationGuard(t *testing.T) {
	reader := &staticAccountSecurityReader{}
	handler := (&UserHandler{accountSecurity: reader}).enforceAccountSecurity(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	response := executeAccountSecurityRequest(
		t,
		handler,
		rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor:  operation.ActorContext{AccountID: "product-ops"},
		},
	)
	if response.Code != http.StatusNoContent || reader.calls != 0 {
		t.Fatalf("service principal must bypass end-user account gate: code=%d calls=%d", response.Code, reader.calls)
	}
}

func executeAccountSecurityRequest(
	t *testing.T,
	handler http.Handler,
	principal rtauth.Principal,
) *httptest.ResponseRecorder {
	return executeAccountSecurityRequestForOperation(
		t,
		handler,
		principal,
		"",
	)
}

func executeAccountSecurityRequestForOperation(
	t *testing.T,
	handler http.Handler,
	principal rtauth.Principal,
	operationID string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodGet, "/user/profile/account-1", nil)
	ctx := rtauth.WithPrincipal(request.Context(), principal)
	if operationID != "" {
		ctx = operation.WithContext(ctx, operation.Context{
			OperationID: operationID,
			Actor:       principal.Actor,
		})
	}
	request = request.WithContext(ctx)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}
