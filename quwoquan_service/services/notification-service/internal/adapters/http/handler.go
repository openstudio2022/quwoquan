package httpadapter

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/notification-service/internal/application"
	generated "quwoquan_service/services/notification-service/internal/generated"
)

type Handler struct {
	appMessageCommands *application.AppMessageCommandFacade
	appMessageQueries  *application.AppMessageQueryFacade
	deliveryCommands   *application.NotificationDeliveryJobCommandFacade
	deliveryQueries    *application.NotificationDeliveryJobQueryFacade
}

type HandlerDependencies struct {
	AppMessageCommands *application.AppMessageCommandFacade
	AppMessageQueries  *application.AppMessageQueryFacade
	DeliveryCommands   *application.NotificationDeliveryJobCommandFacade
	DeliveryQueries    *application.NotificationDeliveryJobQueryFacade
}

func NewHandler(dependencies HandlerDependencies) (*Handler, error) {
	if dependencies.AppMessageCommands == nil {
		return nil, fmt.Errorf("app message command facade is required")
	}
	if dependencies.AppMessageQueries == nil {
		return nil, fmt.Errorf("app message query facade is required")
	}
	if dependencies.DeliveryCommands == nil {
		return nil, fmt.Errorf("notification delivery command facade is required")
	}
	if dependencies.DeliveryQueries == nil {
		return nil, fmt.Errorf("notification delivery query facade is required")
	}
	return &Handler{
		appMessageCommands: dependencies.AppMessageCommands,
		appMessageQueries:  dependencies.AppMessageQueries,
		deliveryCommands:   dependencies.DeliveryCommands,
		deliveryQueries:    dependencies.DeliveryQueries,
	}, nil
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /internal/v1/app-messages", h.handleCreateAppMessage)
	mux.HandleFunc("GET /v1/app-messages", h.handleListAppMessages)
	mux.HandleFunc("GET /v1/app-messages/unread-count", h.handleUnreadCount)
	mux.HandleFunc("GET /v1/app-messages/{messageId}", h.handleGetAppMessage)
	mux.HandleFunc("POST /v1/app-messages/{messageId}/ack", h.handleAckAppMessage)
	mux.HandleFunc("POST /v1/app-messages/{messageId}/read", h.handleReadAppMessage)
	mux.HandleFunc("GET /internal/v1/notifications/delivery-jobs/metrics", h.handleMetrics)
	mux.HandleFunc("GET /internal/v1/notifications/delivery-jobs/dead-letters", h.handleListDeadLetters)
	mux.HandleFunc(
		"POST /internal/v1/notifications/delivery-jobs/{jobAction}",
		h.handleRecoverDeliveryJob,
	)
	return mux
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
		UserID:      actorAccountID(r),
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
	message, err := h.appMessageQueries.GetDetail(r.Context(), actorAccountID(r), r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleAckAppMessage(w http.ResponseWriter, r *http.Request) {
	message, err := h.appMessageCommands.Acknowledge(r.Context(), actorAccountID(r), r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleReadAppMessage(w http.ResponseWriter, r *http.Request) {
	message, err := h.appMessageCommands.MarkRead(r.Context(), actorAccountID(r), r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleUnreadCount(w http.ResponseWriter, r *http.Request) {
	slice, err := h.appMessageQueries.GetUnreadCount(r.Context(), actorAccountID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleMetrics(w http.ResponseWriter, r *http.Request) {
	snapshot, err := h.deliveryQueries.GetMetrics(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, snapshot)
}

func (h *Handler) handleListDeadLetters(w http.ResponseWriter, r *http.Request) {
	limit, err := parseLimit(r.URL.Query().Get("limit"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	slice, err := h.deliveryQueries.ListDeadLetters(
		r.Context(),
		r.URL.Query()["eventType"],
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleRecoverDeliveryJob(w http.ResponseWriter, r *http.Request) {
	jobAction := strings.TrimSpace(r.PathValue("jobAction"))
	if !strings.HasSuffix(jobAction, ":recover") {
		writeHTTPError(w, r, generated.AppErrorFromInvalidArgument("delivery job action must be :recover"))
		return
	}
	jobID := strings.TrimSuffix(jobAction, ":recover")
	result, err := h.deliveryCommands.RecoverDeliveryJob(
		r.Context(),
		jobID,
		r.Header.Get("Idempotency-Key"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func actorAccountID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
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
