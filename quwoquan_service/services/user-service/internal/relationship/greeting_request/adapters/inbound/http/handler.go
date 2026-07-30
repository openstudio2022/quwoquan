package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
)

type Handler struct {
	service *greetingapp.GreetingService
}

func NewHandler(service *greetingapp.GreetingService) (*Handler, error) {
	if service == nil {
		return nil, errors.New("greeting service is required")
	}
	return &Handler{service: service}, nil
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /user/greeting-request", handler.handleSendGreeting)
	mux.HandleFunc("GET /user/greeting-request/inbox", handler.handleListGreetingInbox)
	mux.HandleFunc("GET /user/greeting-request/outbox", handler.handleListGreetingOutbox)
	mux.HandleFunc("POST /user/greeting-request/{requestId}/reply", handler.handleReplyGreeting)
	mux.HandleFunc("POST /user/greeting-request/{requestId}/ignore", handler.handleIgnoreGreeting)
	mux.HandleFunc("DELETE /user/greeting-request/{requestId}", handler.handleCancelGreeting)
}

func (handler *Handler) handleSendGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := actorPersonaID(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	targetID := strings.TrimSpace(anyString(body["targetPersonaId"]))
	if targetID == "" {
		writeInvalidArg(w, r, "targetPersonaId required")
		return
	}
	greeting, err := handler.service.Send(r.Context(), greetingapp.SendGreetingRequest{
		RequesterPersonaID: actorID,
		TargetPersonaID:    targetID,
		RequestMessage:     anyString(body["requestMessage"]),
		Source:             anyString(body["source"]),
		IdempotencyKey:     idempotencyKey(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, greeting)
}

func actorPersonaID(r *http.Request) (string, error) {
	current, ok := operation.FromContext(r.Context())
	if !ok || strings.TrimSpace(current.Actor.PersonaID) == "" {
		return "", usergenerated.AppErrorFromInvalidArgument("active persona context is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func idempotencyKey(r *http.Request) string {
	if current, ok := operation.FromContext(r.Context()); ok {
		if key := strings.TrimSpace(current.IdempotencyKey); key != "" {
			return key
		}
	}
	return strings.TrimSpace(r.Header.Get("Idempotency-Key"))
}

func parseLimit(r *http.Request, fallback int) int {
	value, err := strconv.Atoi(strings.TrimSpace(r.URL.Query().Get("limit")))
	if err != nil || value <= 0 || value > 100 {
		return fallback
	}
	return value
}

func parseCursor(r *http.Request) string {
	return strings.TrimSpace(r.URL.Query().Get("cursor"))
}

func anyString(value any) string {
	text, _ := value.(string)
	return text
}

func readBody(r *http.Request) (map[string]any, error) {
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		return nil, err
	}
	return body, nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeInvalidArg(w http.ResponseWriter, r *http.Request, message string) {
	writeHTTPError(w, r, usergenerated.AppErrorFromInvalidArgument(message))
}

func (handler *Handler) handleListGreetingInbox(w http.ResponseWriter, r *http.Request) {
	actorID, err := actorPersonaID(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items, next, err := handler.service.ListInbox(
		r.Context(),
		actorID,
		r.URL.Query().Get("status"),
		parseCursor(r),
		parseLimit(r, 20),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": next, "nextCursor": next})
}

func (handler *Handler) handleListGreetingOutbox(w http.ResponseWriter, r *http.Request) {
	actorID, err := actorPersonaID(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items, next, err := handler.service.ListOutbox(
		r.Context(),
		actorID,
		r.URL.Query().Get("status"),
		parseCursor(r),
		parseLimit(r, 20),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": next, "nextCursor": next})
}

func (handler *Handler) handleReplyGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := actorPersonaID(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	requestID := strings.TrimSpace(r.PathValue("requestId"))
	greeting, err := handler.service.Reply(r.Context(), actorID, requestID, idempotencyKey(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, greeting)
}

func (handler *Handler) handleIgnoreGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := actorPersonaID(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	requestID := strings.TrimSpace(r.PathValue("requestId"))
	greeting, err := handler.service.Ignore(r.Context(), actorID, requestID, idempotencyKey(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, greeting)
}

func (handler *Handler) handleCancelGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := actorPersonaID(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	requestID := strings.TrimSpace(r.PathValue("requestId"))
	greeting, err := handler.service.Cancel(r.Context(), actorID, requestID, idempotencyKey(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, greeting)
}
