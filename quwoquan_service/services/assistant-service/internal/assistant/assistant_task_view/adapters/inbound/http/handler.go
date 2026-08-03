package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	taskerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_task_view"
	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
)

type Handler struct{ queries *taskapplication.QueryFacade }

func NewHandler(queries *taskapplication.QueryFacade) *Handler {
	return &Handler{queries: queries}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /assistant/tasks", h.listTasks)
}

func (h *Handler) listTasks(w http.ResponseWriter, r *http.Request) {
	accountID, err := taskAccountID(r)
	if err != nil {
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	limit := 32
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		if parsed, parseErr := strconv.Atoi(raw); parseErr == nil {
			limit = parsed
		}
	}
	view, err := h.queries.ListTasks(
		r.Context(), accountID,
		strings.TrimSpace(r.URL.Query().Get("status")), limit,
	)
	if err != nil {
		err = taskerrors.AppErrorFromTaskProjectionUnavailable(err.Error())
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(view)
}

func taskAccountID(r *http.Request) (string, error) {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if value := strings.TrimSpace(principal.Actor.AccountID); value != "" {
			return value, nil
		}
		if value := strings.TrimSpace(principal.Subject); value != "" {
			return value, nil
		}
	}
	return "", taskerrors.AppErrorFromTaskUnauthorized("trusted account principal is required")
}
