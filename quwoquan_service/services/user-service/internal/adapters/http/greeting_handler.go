package http

import (
	"net/http"
	"strings"

	"quwoquan_service/services/user-service/internal/application"
)

func (h *UserHandler) registerGreetingRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /v1/user/greeting-request", h.handleSendGreeting)
	mux.HandleFunc("GET /v1/user/greeting-request/inbox", h.handleListGreetingInbox)
	mux.HandleFunc("GET /v1/user/greeting-request/outbox", h.handleListGreetingOutbox)
	mux.HandleFunc("POST /v1/user/greeting-request/{requestId}/reply", h.handleReplyGreeting)
	mux.HandleFunc("POST /v1/user/greeting-request/{requestId}/ignore", h.handleIgnoreGreeting)
	mux.HandleFunc("DELETE /v1/user/greeting-request/{requestId}", h.handleCancelGreeting)
}

func (h *UserHandler) handleSendGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	targetID := strings.TrimSpace(anyString(body["targetSubAccountId"]))
	if targetID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	greeting, err := h.greeting.Send(r.Context(), application.SendGreetingRequest{
		RequesterSubAccountID: actorID,
		TargetSubAccountID:    targetID,
		RequestMessage:        anyString(body["requestMessage"]),
		Source:                anyString(body["source"]),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, greeting)
}

func (h *UserHandler) handleListGreetingInbox(w http.ResponseWriter, r *http.Request) {
	actorID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items, next, err := h.greeting.ListInbox(
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

func (h *UserHandler) handleListGreetingOutbox(w http.ResponseWriter, r *http.Request) {
	actorID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items, next, err := h.greeting.ListOutbox(
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

func (h *UserHandler) handleReplyGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	requestID := strings.TrimSpace(r.PathValue("requestId"))
	greeting, err := h.greeting.Reply(r.Context(), actorID, requestID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, greeting)
}

func (h *UserHandler) handleIgnoreGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	requestID := strings.TrimSpace(r.PathValue("requestId"))
	greeting, err := h.greeting.Ignore(r.Context(), actorID, requestID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, greeting)
}

func (h *UserHandler) handleCancelGreeting(w http.ResponseWriter, r *http.Request) {
	actorID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	requestID := strings.TrimSpace(r.PathValue("requestId"))
	greeting, err := h.greeting.Cancel(r.Context(), actorID, requestID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, greeting)
}
