package httpadapter

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	jobgenerated "quwoquan_service/services/notification-service/generated/notification_delivery/notification_delivery_job"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

type Handler struct {
	commands *application.NotificationDeliveryJobCommandFacade
	queries  *application.NotificationDeliveryJobQueryFacade
}

func NewHandler(
	commands *application.NotificationDeliveryJobCommandFacade,
	queries *application.NotificationDeliveryJobQueryFacade,
) (*Handler, error) {
	if commands == nil {
		return nil, errors.New("notification delivery command facade is required")
	}
	if queries == nil {
		return nil, errors.New("notification delivery query facade is required")
	}
	return &Handler{commands: commands, queries: queries}, nil
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /internal/notifications/delivery-jobs/metrics", handler.metrics)
	mux.HandleFunc("GET /internal/notifications/delivery-jobs/incoming-call-timeline", handler.incomingCallTimeline)
	mux.HandleFunc("GET /internal/notifications/delivery-jobs/dead-letters", handler.listDeadLetters)
	mux.HandleFunc("POST /internal/notifications/delivery-jobs/{jobAction}", handler.recover)
}

func (handler *Handler) incomingCallTimeline(w http.ResponseWriter, r *http.Request) {
	timeline, err := handler.queries.GetIncomingCallTimeline(
		r.Context(),
		r.URL.Query().Get("callId"),
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, timeline)
}

func (handler *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	return mux
}

func (handler *Handler) metrics(w http.ResponseWriter, r *http.Request) {
	snapshot, err := handler.queries.GetMetrics(r.Context())
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, snapshot)
}

func (handler *Handler) listDeadLetters(w http.ResponseWriter, r *http.Request) {
	limit, err := parseLimit(r.URL.Query().Get("limit"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	slice, err := handler.queries.ListDeadLetters(
		r.Context(),
		r.URL.Query()["eventType"],
		limit,
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (handler *Handler) recover(w http.ResponseWriter, r *http.Request) {
	jobAction := strings.TrimSpace(r.PathValue("jobAction"))
	if !strings.HasSuffix(jobAction, ":recover") {
		writeError(w, r, jobgenerated.AppErrorFromDeliveryJobInvalidArgument("delivery job action must be :recover"))
		return
	}
	result, err := handler.commands.RecoverDeliveryJob(
		r.Context(),
		strings.TrimSuffix(jobAction, ":recover"),
		r.Header.Get("Idempotency-Key"),
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func parseLimit(raw string) (int, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return 20, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 {
		return 0, jobgenerated.AppErrorFromDeliveryJobInvalidArgument("limit must be a positive integer")
	}
	return limit, nil
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
