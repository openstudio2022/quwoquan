package httpadapter

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/notification-service/generated/notification_delivery/notification"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

type Handler struct {
	appMessageCommands *application.AppMessageCommandFacade
	appMessageQueries  *application.AppMessageQueryFacade
}

type HandlerDependencies struct {
	AppMessageCommands *application.AppMessageCommandFacade
	AppMessageQueries  *application.AppMessageQueryFacade
}

func NewHandler(dependencies HandlerDependencies) (*Handler, error) {
	if dependencies.AppMessageCommands == nil {
		return nil, fmt.Errorf("app message command facade is required")
	}
	if dependencies.AppMessageQueries == nil {
		return nil, fmt.Errorf("app message query facade is required")
	}
	return &Handler{
		appMessageCommands: dependencies.AppMessageCommands,
		appMessageQueries:  dependencies.AppMessageQueries,
	}, nil
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return mux
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /internal/app-messages", h.handleCreateAppMessage)
	mux.HandleFunc("GET /app-messages", h.handleListAppMessages)
	mux.HandleFunc("GET /app-messages/unread-count", h.handleUnreadCount)
	mux.HandleFunc("GET /app-messages/{messageId}", h.handleGetAppMessage)
	mux.HandleFunc("POST /app-messages/{messageId}/ack", h.handleAckAppMessage)
	mux.HandleFunc("POST /app-messages/{messageId}/read", h.handleReadAppMessage)
}

func (h *Handler) handleCreateAppMessage(w http.ResponseWriter, r *http.Request) {
	var command application.CreateAppMessageCommand
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&command); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	command.IdempotencyKey = strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	message, err := h.appMessageCommands.Create(r.Context(), command)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, message)
}

func (h *Handler) handleListAppMessages(w http.ResponseWriter, r *http.Request) {
	accountID, ok := authenticatedAccountID(w, r)
	if !ok {
		return
	}
	limit, err := parseLimit(r.URL.Query().Get("limit"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	read, err := parseOptionalBool(r.URL.Query().Get("read"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	slice, err := h.appMessageQueries.ListInbox(r.Context(), application.AppMessageInboxQuery{
		UserID:      accountID,
		MessageType: r.URL.Query().Get("type"),
		Read:        read,
		Cursor:      r.URL.Query().Get("cursor"),
		Limit:       limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleGetAppMessage(w http.ResponseWriter, r *http.Request) {
	accountID, ok := authenticatedAccountID(w, r)
	if !ok {
		return
	}
	message, err := h.appMessageQueries.GetDetail(r.Context(), accountID, r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleAckAppMessage(w http.ResponseWriter, r *http.Request) {
	accountID, ok := authenticatedAccountID(w, r)
	if !ok {
		return
	}
	message, err := h.appMessageCommands.Acknowledge(r.Context(), accountID, r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleReadAppMessage(w http.ResponseWriter, r *http.Request) {
	accountID, ok := authenticatedAccountID(w, r)
	if !ok {
		return
	}
	message, err := h.appMessageCommands.MarkRead(r.Context(), accountID, r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleUnreadCount(w http.ResponseWriter, r *http.Request) {
	accountID, ok := authenticatedAccountID(w, r)
	if !ok {
		return
	}
	slice, err := h.appMessageQueries.GetUnreadCount(r.Context(), accountID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func authenticatedAccountID(w http.ResponseWriter, r *http.Request) (string, bool) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	accountID := ""
	if ok {
		accountID = strings.TrimSpace(principal.Actor.AccountID)
	}
	if accountID == "" {
		writeHTTPError(
			w,
			r,
			generated.AppErrorFromUnauthorized(
				"app message inbox requires a trusted account principal",
			),
		)
		return "", false
	}
	return accountID, true
}

func parseLimit(raw string) (int, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return 20, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 {
		return 0, generated.AppErrorFromInvalidArgument("limit must be a positive integer")
	}
	return limit, nil
}

func parseOptionalBool(raw string) (*bool, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	value, err := strconv.ParseBool(raw)
	if err != nil {
		return nil, generated.AppErrorFromInvalidArgument("read must be true or false")
	}
	return &value, nil
}
