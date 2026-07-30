package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/rtc-service/generated/rtc/call_session"
	transport "quwoquan_service/services/rtc-service/generated/rtc/call_session/transport"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application/commandmeta"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
)

type CallHandler struct {
	orchestrator *application.CallOrchestrator
}

func NewCallHandler(orch *application.CallOrchestrator) *CallHandler {
	return &CallHandler{orchestrator: orch}
}

func (h *CallHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)

	for _, r := range transport.RouteTable {
		route := r
		pattern := route.Method + " " + route.Template
		mux.HandleFunc(pattern, func(w http.ResponseWriter, req *http.Request) {
			if key := req.Header.Get("Idempotency-Key"); key != "" {
				req = req.WithContext(commandmeta.WithIdempotencyKey(req.Context(), key))
			}
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
	case "ReportMediaConnected":
		h.handleReportMediaConnected(w, r)
	case "GetCall":
		h.handleGetCall(w, r)
	case "ListCalls":
		h.handleListCalls(w, r)
	case "ToggleMute":
		h.handleToggleMute(w, r)
	case "ToggleCamera":
		h.handleToggleCamera(w, r)
	case "StartScreenShare":
		h.handleStartScreenShare(w, r)
	case "StopScreenShare":
		h.handleStopScreenShare(w, r)
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleRTC, "接口不存在", "route not found"))
	}
}

func (h *CallHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// ── Call Lifecycle ───────────────────────────────────────────────────────────

func (h *CallHandler) handleInitiateCall(w http.ResponseWriter, r *http.Request) {
	var body struct {
		CallType        string   `json:"callType"`
		ConversationID  string   `json:"conversationId"`
		CircleID        string   `json:"circleId"`
		InviteeIDs      []string `json:"inviteeIds"`
		MaxParticipants int      `json:"maxParticipants"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}

	resp, err := h.orchestrator.InitiateCall(r.Context(), application.InitiateCallRequest{
		InitiatorID:     resolveUserID(r),
		CallType:        body.CallType,
		ConversationID:  body.ConversationID,
		CircleID:        body.CircleID,
		InviteeIDs:      body.InviteeIDs,
		MaxParticipants: body.MaxParticipants,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, resp)
}

func (h *CallHandler) handleAnswerCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	resp, err := h.orchestrator.AnswerCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *CallHandler) handleRejectCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.RejectCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleCancelCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.CancelCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleHangupCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.HangupCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleJoinCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	result, err := h.orchestrator.JoinCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *CallHandler) handleLeaveCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.LeaveCall(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleReportMediaConnected(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.ReportMediaConnected(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}
	session, err := h.orchestrator.InviteToCall(r.Context(), callID, resolveUserID(r), body.InviteeIDs)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

// ── Query ────────────────────────────────────────────────────────────────────

func (h *CallHandler) handleGetCall(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.GetCall(
		r.Context(),
		callID,
		resolveUserID(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleListCalls(w http.ResponseWriter, r *http.Request) {
	userID := resolveUserID(r)
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)
	filter := application.ListCallsFilter{
		Status:     r.URL.Query().Get("status"),
		MissedOnly: r.URL.Query().Get("missed") == "true",
	}

	page, err := h.orchestrator.ListCalls(r.Context(), userID, limit, cursor, filter)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

// ── Media Controls ───────────────────────────────────────────────────────────

func (h *CallHandler) handleToggleMute(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	var body struct {
		Muted *bool `json:"muted"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}
	if body.Muted == nil {
		writeHTTPError(
			w,
			r,
			rterr.NewInvalidArgument(
				rterr.ModuleRTC,
				"请求格式错误",
				"muted is required",
			),
		)
		return
	}
	session, err := h.orchestrator.ToggleMute(r.Context(), callID, resolveUserID(r), *body.Muted)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleToggleCamera(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	var body struct {
		CameraOn *bool `json:"cameraOn"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleRTC, "请求格式错误", err.Error()))
		return
	}
	if body.CameraOn == nil {
		writeHTTPError(
			w,
			r,
			rterr.NewInvalidArgument(
				rterr.ModuleRTC,
				"请求格式错误",
				"cameraOn is required",
			),
		)
		return
	}
	session, err := h.orchestrator.ToggleCamera(r.Context(), callID, resolveUserID(r), *body.CameraOn)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

// ── Screen Share ─────────────────────────────────────────────────────────────

func (h *CallHandler) handleStartScreenShare(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.StartScreenShare(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *CallHandler) handleStopScreenShare(w http.ResponseWriter, r *http.Request) {
	callID := r.PathValue("callId")
	session, err := h.orchestrator.StopScreenShare(r.Context(), callID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// resolveUserID 只信任 auth middleware 从验签 token 重建的 Principal，
// 不读取客户端上送的身份 header。
func resolveUserID(r *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		return principal.Actor.PersonaID
	}
	return ""
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		err = generated.AppErrorFromInternalError(err.Error())
	}
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func readJSON(r *http.Request, v any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
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
