package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/rtc-service/internal/adapters/ws"
	"quwoquan_service/services/rtc-service/internal/application"
)

type CallHandler struct {
	orchestrator *application.CallOrchestrator
	signalHandler *ws.SignalHandler
}

func NewCallHandler(orch *application.CallOrchestrator, sh *ws.SignalHandler) *CallHandler {
	return &CallHandler{orchestrator: orch, signalHandler: sh}
}

func (h *CallHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)
	if h.signalHandler != nil {
		mux.HandleFunc("/v1/rtc/signal", h.signalHandler.HandleSignal)
	}

	for _, r := range generatedRouteTable {
		route := r
		pattern := route.Method + " " + route.Template
		mux.HandleFunc(pattern, func(w http.ResponseWriter, req *http.Request) {
			h.dispatchOperation(route.Operation, w, req)
		})
	}
	return mux
}

func (h *CallHandler) dispatchOperation(operation string, w http.ResponseWriter, r *http.Request) {
	switch operation {
	case "InitiateCall":
		h.handleInitiateCall(w, r)
	case "AnswerCall":
		h.handleAnswerCall(w, r)
	case "RejectCall":
		h.handleRejectCall(w, r)
	case "CancelCall":
		h.handleCancelCall(w, r)
	case "HangupCall":
		h.handleHangupCall(w, r)
	case "JoinCall":
		h.handleJoinCall(w, r)
	case "LeaveCall":
		h.handleLeaveCall(w, r)
	case "InviteToCall":
		h.handleInviteToCall(w, r)
	case "GetCall":
		h.handleGetCall(w, r)
	case "ListCalls":
		h.handleListCalls(w, r)
	case "ToggleMute":
		h.handleToggleMute(w, r)
	case "ToggleCamera":
		h.handleToggleCamera(w, r)
	case "StartRecording":
		h.handleStartRecording(w, r)
	case "StopRecording":
		h.handleStopRecording(w, r)
	case "StartScreenShare":
		h.handleStartScreenShare(w, r)
	case "StopScreenShare":
		h.handleStopScreenShare(w, r)
	default:
		http.NotFound(w, r)
	}
}

func (h *CallHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// ── Call Lifecycle ───────────────────────────────────────────────────────────

func (h *CallHandler) handleInitiateCall(w http.ResponseWriter, r *http.Request) {
	var body struct {
		CallType       string   `json:"callType"`
		ConversationID string   `json:"conversationId"`
		CircleID       string   `json:"circleId"`
		InviteeIDs     []string `json:"inviteeIds"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}

	resp, err := h.orchestrator.InitiateCall(r.Context(), application.InitiateCallRequest{
		InitiatorID:    resolveUserID(r),
		CallType:       body.CallType,
		ConversationID: body.ConversationID,
		CircleID:       body.CircleID,
		InviteeIDs:     body.InviteeIDs,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, resp)
}

func (h *CallHandler) handleAnswerCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	resp, err := h.orchestrator.AnswerCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *CallHandler) handleRejectCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.RejectCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleCancelCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.CancelCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleHangupCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.HangupCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleJoinCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, token, err := h.orchestrator.JoinCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"session": session, "token": token})
}

func (h *CallHandler) handleLeaveCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.LeaveCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleInviteToCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	var body struct {
		InviteeIDs []string `json:"inviteeIds"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}
	session, err := h.orchestrator.InviteToCall(r.Context(), callID, resolveUserID(r), body.InviteeIDs)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

// ── Query ────────────────────────────────────────────────────────────────────

func (h *CallHandler) handleGetCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.GetCall(r.Context(), callID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleListCalls(w http.ResponseWriter, r *http.Request) {
	userID := resolveUserID(r)
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)

	calls, err := h.orchestrator.ListCalls(r.Context(), userID, limit, cursor)
	if err != nil {
		writeHTTPError(w, err)
		return
	}

	nextCursor := ""
	if len(calls) > 0 {
		nextCursor = calls[len(calls)-1].ID
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": calls, "cursor": nextCursor})
}

// ── Media Controls ───────────────────────────────────────────────────────────

func (h *CallHandler) handleToggleMute(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	var body application.ToggleMuteRequest
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}
	session, err := h.orchestrator.ToggleMute(r.Context(), callID, resolveUserID(r), body.Muted)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleToggleCamera(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	var body application.ToggleCameraRequest
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}
	session, err := h.orchestrator.ToggleCamera(r.Context(), callID, resolveUserID(r), body.CameraOn)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

// ── Recording ────────────────────────────────────────────────────────────────

func (h *CallHandler) handleStartRecording(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.StartRecording(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleStopRecording(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.StopRecording(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

// ── Screen Share ─────────────────────────────────────────────────────────────

func (h *CallHandler) handleStartScreenShare(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.StartScreenShare(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleStopScreenShare(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.StopScreenShare(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

// ── Helpers ──────────────────────────────────────────────────────────────────

func resolveUserID(r *http.Request) string {
	return r.Header.Get("X-Client-User-Id")
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func writeHTTPError(w http.ResponseWriter, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptions{})
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

func queryInt(r *http.Request, key string, defaultVal int) int {
	s := r.URL.Query().Get(key)
	if s == "" {
		return defaultVal
	}
	v, err := strconv.Atoi(s)
	if err != nil {
		return defaultVal
	}
	return v
}
