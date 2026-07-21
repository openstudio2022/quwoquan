package http

import (
	"net/http"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	accountlifecycleapp "quwoquan_service/services/user-service/internal/application/account/user_account"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

// registerAccountLifecycleRoutes 挂载 UserAccount 生命周期终态命令。
// path 真相源：contracts/metadata/user/user_profile/service.yaml CloseAccount。
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
		"user.user_profile.SuspendAccount",
		accountports.EnforcementActionSuspend,
	)
}

func (h *UserHandler) handleRestoreAccount(w http.ResponseWriter, r *http.Request) {
	h.handleAccountEnforcement(
		w,
		r,
		"user.user_profile.RestoreAccount",
		accountports.EnforcementActionRestore,
	)
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
		outcome, err = h.accountEnforcement.SuspendAccount(r.Context(), command)
	} else {
		outcome, err = h.accountEnforcement.RestoreAccount(r.Context(), command)
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
