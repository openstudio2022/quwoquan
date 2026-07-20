package http

import (
	"net/http"
	"strings"
	"time"

	accountlifecycleapp "quwoquan_service/services/user-service/internal/application/account/user_account"
	"quwoquan_service/services/user-service/internal/generated"
)

// registerAccountLifecycleRoutes 挂载 UserAccount 生命周期终态命令。
// path 真相源：contracts/metadata/user/user_profile/service.yaml CloseAccount。
func (h *UserHandler) registerAccountLifecycleRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /owner/account/close", h.handleCloseAccount)
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
