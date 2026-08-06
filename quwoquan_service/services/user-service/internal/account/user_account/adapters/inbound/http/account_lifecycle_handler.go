package http

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/user-service/generated/account/user_account"
	accountlifecycleapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

const (
	accountSecurityReadOperationID   = "user.user_account.ReadAccountSecurity"
	accountSecurityHealthOperationID = "user.user_account.CheckAccountSecurityAuthority"
	accountSecurityReadScope         = "user.account.security.read"
	accountSecurityHealthProbeID     = "__account_security_authority_readiness_probe__"
	accountEnforcementWriteScope     = "user.account.enforcement.write"
	productOpsServicePrincipal       = "service:product-ops-service"
)

func isAuthorizedAccountSecurityAuthorityCaller(accountID string) bool {
	switch strings.TrimSpace(accountID) {
	case "service:api-edge",
		"service:assistant-service",
		"service:chat-service",
		"service:circle-service",
		"service:content-service",
		"service:entity-service",
		"service:integration-service",
		"service:notification-service",
		"service:product-ops-service",
		"service:realtime-gateway",
		"service:rtc-service",
		"service:search-service",
		"service:tag-service":
		return true
	default:
		return false
	}
}

// registerAccountLifecycleRoutes 挂载 UserAccount 生命周期终态命令。
// path 真相源：services/user-service/contracts/account/user_account/operations.yaml CloseAccount。
func (h *UserHandler) registerAccountLifecycleRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /owner/account/close", h.handleCloseAccount)
	mux.HandleFunc(
		"POST /internal/user/accounts/{userId}/suspend",
		h.handleSuspendAccount,
	)
	mux.HandleFunc(
		"POST /internal/user/accounts/{userId}/restore",
		h.handleRestoreAccount,
	)
	mux.HandleFunc(
		"GET /internal/user/accounts/{userId}/security",
		h.handleReadAccountSecurity,
	)
	mux.HandleFunc(
		"GET /internal/user/account-security/health",
		h.handleAccountSecurityAuthorityHealth,
	)
}

func (h *UserHandler) handleCloseAccount(w http.ResponseWriter, r *http.Request) {
	if h.accountLifecycle == nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError(
			"account lifecycle facade is unavailable",
		))
		return
	}
	accountID := strings.TrimSpace(userIDFromHeader(r))
	if accountID == "" {
		writeHTTPError(w, r, generated.AppErrorFromUnauthorized(
			"close account requires an authenticated principal",
		))
		return
	}
	outcome, err := h.accountLifecycle.CloseAccount(
		r.Context(),
		accountlifecycleapp.CloseCommand{AccountID: accountID},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"accountState":     outcome.AccountState,
		"closedAt":         outcome.ClosedAt.UTC().Format(time.RFC3339),
		"idempotentReplay": outcome.IdempotentReplay,
	})
}

type accountEnforcementDecisionRequest struct {
	DecisionID     string    `json:"decisionId"`
	CaseRef        string    `json:"caseRef"`
	DecisionDigest string    `json:"decisionDigest"`
	ApprovedAt     time.Time `json:"approvedAt"`
}

func (h *UserHandler) handleSuspendAccount(w http.ResponseWriter, r *http.Request) {
	h.handleAccountEnforcement(
		w,
		r,
		"user.user_account.SuspendAccount",
		accountports.EnforcementActionSuspend,
	)
}

func (h *UserHandler) handleRestoreAccount(w http.ResponseWriter, r *http.Request) {
	h.handleAccountEnforcement(
		w,
		r,
		"user.user_account.RestoreAccount",
		accountports.EnforcementActionRestore,
	)
}

// handleReadAccountSecurity serves the intentionally minimal, service-only
// authority read used by resource middleware after JWT verification. The
// handler must never return account/profile/persona/device/credential data.
func (h *UserHandler) handleReadAccountSecurity(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedAccountSecurityAuthorityOperationContext(
		w,
		r,
		accountSecurityReadOperationID,
	)
	if !ok {
		return
	}
	if h.accountSecurity == nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError(
			"account security authority is unavailable",
		))
		return
	}
	snapshot, err := h.accountSecurity.ReadAccountSecurity(
		ctx,
		strings.TrimSpace(r.PathValue("userId")),
	)
	if errors.Is(err, accountports.ErrAccountNotFound) {
		writeHTTPError(w, r, generated.AppErrorFromUserNotFound(
			"account security subject not found",
		))
		return
	}
	if err != nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError(
			"account security authority read failed",
		))
		return
	}
	w.Header().Set("Cache-Control", "no-store, max-age=0")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	writeJSON(w, http.StatusOK, map[string]any{
		"accountState": snapshot.AccountState,
		"authEpoch":    snapshot.AuthEpoch,
	})
}

// handleAccountSecurityAuthorityHealth verifies a resource service's scoped
// authority credential and the backing UserAccount reader without exposing a
// real account or cached state.
func (h *UserHandler) handleAccountSecurityAuthorityHealth(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedAccountSecurityAuthorityOperationContext(
		w,
		r,
		accountSecurityHealthOperationID,
	)
	if !ok {
		return
	}
	if h.accountSecurity == nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError(
			"account security authority is unavailable",
		))
		return
	}
	_, err := h.accountSecurity.ReadAccountSecurity(ctx, accountSecurityHealthProbeID)
	if err != nil && !errors.Is(err, accountports.ErrAccountNotFound) {
		writeHTTPError(w, r, generated.AppErrorFromInternalError(
			"account security authority readiness read failed",
		))
		return
	}
	w.Header().Set("Cache-Control", "no-store, max-age=0")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func trustedAccountSecurityAuthorityOperationContext(
	w http.ResponseWriter,
	r *http.Request,
	expectedOperation string,
) (context.Context, bool) {
	ctx, ok := trustedServiceOperationContext(
		w,
		r,
		expectedOperation,
		accountSecurityReadScope,
		"",
	)
	if !ok {
		return nil, false
	}
	principal, _ := rtauth.PrincipalFromContext(r.Context())
	if isAuthorizedAccountSecurityAuthorityCaller(principal.Actor.AccountID) {
		return ctx, true
	}
	writeHTTPError(w, r, generated.AppErrorFromForbidden(
		"service principal is not authorized for account security authority",
	))
	return nil, false
}

func (h *UserHandler) handleAccountEnforcement(
	w http.ResponseWriter,
	r *http.Request,
	expectedOperationID string,
	action accountports.EnforcementAction,
) {
	if h.accountEnforcement == nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError(
			"account enforcement facade is unavailable",
		))
		return
	}
	invocation, ok := operation.FromContext(r.Context())
	if !ok || invocation.OperationID != expectedOperationID ||
		strings.TrimSpace(invocation.IdempotencyKey) == "" {
		writeHTTPError(w, r, generated.AppErrorFromUnauthorized(
			"trusted account enforcement operation context is required",
		))
		return
	}
	trustedContext, ok := trustedServiceOperationContext(
		w,
		r,
		expectedOperationID,
		accountEnforcementWriteScope,
		productOpsServicePrincipal,
	)
	if !ok {
		return
	}
	accountID := strings.TrimSpace(r.PathValue("userId"))
	if accountID == "" {
		writeHTTPError(w, r, generated.AppErrorFromAccountEnforcementDecisionInvalid(
			"account enforcement requires an account id",
		))
		return
	}
	var request accountEnforcementDecisionRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromAccountEnforcementDecisionInvalid(
			"invalid account enforcement request",
		))
		return
	}
	if strings.TrimSpace(invocation.IdempotencyKey) !=
		strings.TrimSpace(request.DecisionID) {
		writeHTTPError(w, r, generated.AppErrorFromAccountEnforcementDecisionInvalid(
			"Idempotency-Key must equal the approved decision id",
		))
		return
	}
	command := accountlifecycleapp.EnforcementCommand{
		AccountID: accountID,
		Action:    action,
		Decision: accountports.EnforcementDecision{
			DecisionID:     request.DecisionID,
			CaseRef:        request.CaseRef,
			DecisionDigest: request.DecisionDigest,
			ApprovedAt:     request.ApprovedAt,
		},
	}
	var (
		outcome accountlifecycleapp.EnforcementOutcome
		err     error
	)
	if action == accountports.EnforcementActionSuspend {
		outcome, err = h.accountEnforcement.SuspendAccount(trustedContext, command)
	} else {
		outcome, err = h.accountEnforcement.RestoreAccount(trustedContext, command)
	}
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"accountState":     outcome.AccountState,
		"authEpoch":        outcome.AuthEpoch,
		"decisionId":       outcome.DecisionID,
		"idempotentReplay": outcome.IdempotentReplay,
		"occurredAt":       outcome.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
}
