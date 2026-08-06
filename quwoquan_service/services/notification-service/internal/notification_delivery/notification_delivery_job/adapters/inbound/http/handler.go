package httpadapter

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	jobgenerated "quwoquan_service/services/notification-service/generated/notification_delivery/notification_delivery_job"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	deliverydomain "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

type Handler struct {
	commands      *application.NotificationDeliveryJobCommandFacade
	queries       *application.NotificationDeliveryJobQueryFacade
	incomingCalls *application.IncomingCallDeliveryCoordinator
}

func (handler *Handler) WithIncomingCallCoordinator(
	coordinator *application.IncomingCallDeliveryCoordinator,
) *Handler {
	if handler == nil || coordinator == nil {
		panic("notification delivery job HTTP handler requires incoming-call coordinator")
	}
	handler.incomingCalls = coordinator
	return handler
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
	if handler.incomingCalls != nil {
		mux.HandleFunc(
			"POST /notifications/incoming-calls/presentation:ack",
			handler.ackIncomingCallPresentation,
		)
	}
	mux.HandleFunc("GET /internal/notifications/delivery-jobs/metrics", handler.metrics)
	mux.HandleFunc("GET /internal/notifications/delivery-jobs/incoming-call-timeline", handler.incomingCallTimeline)
	mux.HandleFunc("GET /internal/notifications/delivery-jobs/dead-letters", handler.listDeadLetters)
	mux.HandleFunc("POST /internal/notifications/delivery-jobs/{jobAction}", handler.recover)
}

func (handler *Handler) ackIncomingCallPresentation(
	w http.ResponseWriter,
	r *http.Request,
) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok ||
		strings.TrimSpace(principal.Actor.AccountID) == "" ||
		strings.TrimSpace(principal.Actor.PersonaID) == "" ||
		strings.TrimSpace(principal.Actor.DeviceActorID) == "" {
		writeError(w, r, jobgenerated.AppErrorFromDeliveryJobUnauthorized(
			"incoming call presentation ACK requires trusted persona and device",
		))
		return
	}
	var command struct {
		DeliveryKey string `json:"deliveryKey"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&command); err != nil ||
		strings.TrimSpace(command.DeliveryKey) == "" {
		debugMessage := "deliveryKey is required"
		if err != nil {
			debugMessage = err.Error()
		}
		writeError(w, r, jobgenerated.AppErrorFromDeliveryJobInvalidArgument(debugMessage))
		return
	}
	result, err := handler.incomingCalls.AckPresentation(
		r.Context(),
		principal.Actor.PersonaID,
		principal.Actor.DeviceActorID,
		command.DeliveryKey,
	)
	if err != nil {
		if errors.Is(err, deliverydomain.ErrDeliveryJobNotFound) {
			writeError(w, r, jobgenerated.AppErrorFromDeliveryJobNotFound(err.Error()))
			return
		}
		writeError(w, r, jobgenerated.AppErrorFromDeliveryJobStorageWriteFailed(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, result)
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
