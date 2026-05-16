package http

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type Handler struct {
	service *application.AssistantService
}

func NewHandler(service *application.AssistantService) *Handler {
	return &Handler{service: service}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)
	mux.HandleFunc("GET /v1/assistant/policy", h.handleGetPolicy)
	mux.HandleFunc("POST /v1/assistant/page-context", h.handleReportPageContext)
	mux.HandleFunc("GET /v1/assistant/suggested-actions", h.handleGetSuggestedActions)
	mux.HandleFunc("POST /v1/assistant/learning/events", h.handleReportInteractionEvent)
	mux.HandleFunc("POST /v1/assistant/learning/scorecards", h.handleReportScorecard)
	mux.HandleFunc("POST /v1/assistant/search/xiaoqu", h.handleSearchXiaoqu)
	mux.HandleFunc("GET /v1/assistant/tasks", h.handleListTasks)
	mux.HandleFunc("GET /v1/assistant/memories", h.handleListMemories)
	mux.HandleFunc("GET /v1/assistant/ops/learning-summary", h.handleGetLearningOpsSummary)
	mux.HandleFunc("GET /v1/assistant/skills", h.handleListSkills)
	mux.HandleFunc("GET /v1/assistant/skill-subscriptions", h.handleListSkillSubscriptions)
	mux.HandleFunc("POST /v1/assistant/skill-subscriptions", h.handleCreateSkillSubscription)
	mux.HandleFunc("POST /v1/assistant/skill-subscriptions/cron/tick", h.handleTickSkillSubscriptionCron)
	mux.HandleFunc("GET /v1/assistant/skill-subscriptions/{subscriptionId}", h.handleGetSkillSubscription)
	mux.HandleFunc("PATCH /v1/assistant/skill-subscriptions/{subscriptionId}/status", h.handleUpdateSkillSubscriptionStatus)
	mux.HandleFunc("GET /v1/assistant/consents", h.handleListConsents)
	mux.HandleFunc("/v1/assistant/skills/", h.handleSkillConsentRoutes)
	mux.HandleFunc("POST /v1/assistant/conversations", h.handleCreateConversation)
	mux.HandleFunc("GET /v1/assistant/conversations/{conversationId}", h.handleGetConversation)
	mux.HandleFunc("POST /v1/assistant/conversations/{conversationId}/turns", h.handleCreateTurn)
	mux.HandleFunc("GET /v1/assistant/turns/{turnId}", h.handleGetTurn)
	mux.HandleFunc("POST /v1/assistant/turns/{turnId}/stream", h.handleStreamTurn)
	mux.HandleFunc("POST /v1/app-messages", h.handleCreateAppMessage)
	mux.HandleFunc("GET /v1/app-messages", h.handleListAppMessages)
	mux.HandleFunc("GET /v1/app-messages/unread-count", h.handleGetAppMessageUnreadCount)
	mux.HandleFunc("GET /v1/app-messages/stream", h.handleStreamAppMessages)
	mux.HandleFunc("GET /v1/app-messages/{messageId}", h.handleGetAppMessage)
	mux.HandleFunc("POST /v1/app-messages/{messageId}/ack", h.handleAckAppMessage)
	mux.HandleFunc("POST /v1/app-messages/{messageId}/read", h.handleReadAppMessage)
	return mux
}

func (h *Handler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *Handler) handleGetPolicy(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.GetPolicy(r.Context(), resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleReportPageContext(w http.ResponseWriter, r *http.Request) {
	var input assistant.PageContextInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	ack, err := h.service.ReportPageContext(r.Context(), resolveUserID(r), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, ack)
}

func (h *Handler) handleGetSuggestedActions(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.GetSuggestedActions(r.Context(), resolveUserID(r), strings.TrimSpace(r.URL.Query().Get("pageType")), strings.TrimSpace(r.URL.Query().Get("objectId")))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleReportInteractionEvent(w http.ResponseWriter, r *http.Request) {
	payload, err := readJSONObject(r)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	events, err := decodeInteractionEvents(payload)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	for i := range events {
		applyInteractionRequestContext(&events[i], r)
	}
	resp, err := h.service.ReportInteractionEvents(r.Context(), events)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) handleReportScorecard(w http.ResponseWriter, r *http.Request) {
	payload, err := readJSONObject(r)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	scores, err := decodeScorecards(payload)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	for i := range scores {
		applyScorecardRequestContext(&scores[i], r)
	}
	resp, err := h.service.ReportScorecards(r.Context(), scores)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) handleSearchXiaoqu(w http.ResponseWriter, r *http.Request) {
	var req assistant.SearchRequest
	if err := readJSON(r, &req); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	view, err := h.service.SearchXiaoquResults(r.Context(), req)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleListTasks(w http.ResponseWriter, r *http.Request) {
	limit := parseLimit(r, 32)
	view, err := h.service.ListAssistantTasks(r.Context(), resolveUserID(r), limit, strings.TrimSpace(r.URL.Query().Get("status")))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleListMemories(w http.ResponseWriter, r *http.Request) {
	limit := parseLimit(r, 32)
	view, err := h.service.ListAssistantMemories(r.Context(), resolveUserID(r), limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleGetLearningOpsSummary(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.GetLearningOpsSummary(r.Context(), resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleListSkills(w http.ResponseWriter, r *http.Request) {
	limit := parseLimit(r, 64)
	view, err := h.service.ListSkills(r.Context(), resolveUserID(r), limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleListSkillSubscriptions(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.ListSkillSubscriptions(
		r.Context(),
		resolveUserID(r),
		strings.TrimSpace(r.URL.Query().Get("status")),
		parseLimit(r, 20),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleCreateSkillSubscription(w http.ResponseWriter, r *http.Request) {
	var input assistant.CreateSkillSubscriptionInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	subscription, err := h.service.CreateSkillSubscription(r.Context(), resolveUserID(r), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, subscription)
}

func (h *Handler) handleGetSkillSubscription(w http.ResponseWriter, r *http.Request) {
	subscription, err := h.service.GetSkillSubscription(r.Context(), resolveUserID(r), r.PathValue("subscriptionId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, subscription)
}

func (h *Handler) handleUpdateSkillSubscriptionStatus(w http.ResponseWriter, r *http.Request) {
	var input assistant.UpdateSkillSubscriptionStatusInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	subscription, err := h.service.UpdateSkillSubscriptionStatus(r.Context(), resolveUserID(r), r.PathValue("subscriptionId"), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, subscription)
}

func (h *Handler) handleTickSkillSubscriptionCron(w http.ResponseWriter, r *http.Request) {
	var input assistant.SkillSubscriptionCronTickInput
	if err := readJSON(r, &input); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	result, err := h.service.TickSkillSubscriptionCron(r.Context(), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleListConsents(w http.ResponseWriter, r *http.Request) {
	items, err := h.service.ListConsents(r.Context(), resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *Handler) handleSkillConsentRoutes(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/v1/assistant/skills/")
	parts := strings.Split(path, "/")
	if len(parts) != 2 || parts[1] != "consent" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "无效路径", "expected /v1/assistant/skills/{skillId}/consent"))
		return
	}
	skillID := strings.TrimSpace(parts[0])
	switch r.Method {
	case http.MethodPost:
		var body struct {
			GrantedScope string `json:"grantedScope"`
		}
		if err := readJSON(r, &body); err != nil && err != io.EOF {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
			return
		}
		consent, err := h.service.GrantSkillConsent(r.Context(), resolveUserID(r), skillID, strings.TrimSpace(body.GrantedScope))
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"consent": consent})
	case http.MethodDelete:
		if err := h.service.RevokeSkillConsent(r.Context(), resolveUserID(r), skillID); err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "skillId": skillID})
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "方法不支持", "only POST/DELETE"))
	}
}

func (h *Handler) handleCreateAppMessage(w http.ResponseWriter, r *http.Request) {
	var input assistant.CreateAppMessageInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	if strings.TrimSpace(input.UserID) == "" {
		input.UserID = resolveUserID(r)
	}
	message, err := h.service.CreateAppMessage(r.Context(), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, message)
}

func (h *Handler) handleListAppMessages(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.ListAppMessages(r.Context(), resolveUserID(r), parseLimit(r, 20), strings.TrimSpace(r.URL.Query().Get("cursor")))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleGetAppMessage(w http.ResponseWriter, r *http.Request) {
	message, err := h.service.GetAppMessage(r.Context(), resolveUserID(r), r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleAckAppMessage(w http.ResponseWriter, r *http.Request) {
	message, err := h.service.AckAppMessage(r.Context(), resolveUserID(r), r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleReadAppMessage(w http.ResponseWriter, r *http.Request) {
	message, err := h.service.ReadAppMessage(r.Context(), resolveUserID(r), r.PathValue("messageId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, message)
}

func (h *Handler) handleGetAppMessageUnreadCount(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.GetAppMessageUnreadCount(r.Context(), resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleStreamAppMessages(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.ListAppMessages(r.Context(), resolveUserID(r), parseLimit(r, 20), "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	envelopes := make([]streaming.Envelope, 0, len(view.Items)+1)
	envelopes = append(envelopes, mustStreamingEnvelope("app_message.stream.ready", 1, map[string]any{
		"status": "ready",
		"count":  len(view.Items),
	}))
	for i, message := range view.Items {
		envelope := mustStreamingEnvelope("app_message.created", uint64(i+2), message)
		envelope.StreamID = "app_messages:" + resolveUserID(r)
		envelope.Topic = "app_message"
		envelopes = append(envelopes, envelope.Normalized())
	}
	writeStreamingSSE(w, r, envelopes)
}

func (h *Handler) handleCreateConversation(w http.ResponseWriter, r *http.Request) {
	var input assistant.CreateConversationInput
	if err := readJSON(r, &input); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	conversation, err := h.service.CreateConversation(r.Context(), resolveUserID(r), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, conversation)
}

func (h *Handler) handleGetConversation(w http.ResponseWriter, r *http.Request) {
	conversation, err := h.service.GetConversation(r.Context(), resolveUserID(r), r.PathValue("conversationId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, conversation)
}

func (h *Handler) handleCreateTurn(w http.ResponseWriter, r *http.Request) {
	var input assistant.CreateTurnInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	turn, err := h.service.CreateTurn(r.Context(), resolveUserID(r), r.PathValue("conversationId"), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	log.Printf("assistant http create_turn conversationId=%s turnId=%s traceId=%s", turn.ConversationID, turn.TurnID, turn.TraceID)
	writeJSON(w, http.StatusCreated, turn)
}

func (h *Handler) handleGetTurn(w http.ResponseWriter, r *http.Request) {
	turn, err := h.service.GetTurn(r.Context(), resolveUserID(r), r.PathValue("turnId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, turn)
}

func (h *Handler) handleStreamTurn(w http.ResponseWriter, r *http.Request) {
	turnID := r.PathValue("turnId")
	if err := readJSON(r, &map[string]any{}); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	log.Printf("assistant http stream_turn_requested turnId=%s requestId=%s traceId=%s", turnID, resolveRequestID(r), resolveTraceID(r))
	flusher, _ := w.(http.Flusher)
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	emitted := 0
	err := h.service.StreamTurn(r.Context(), resolveUserID(r), turnID, func(envelope streaming.Envelope) error {
		emitted++
		writeStreamingSSEEnvelope(w, envelope, flusher)
		return nil
	})
	if err != nil {
		log.Printf("assistant http stream_turn_failed turnId=%s emitted=%d err=%v", turnID, emitted, err)
		return
	}
	log.Printf("assistant http stream_turn_ready turnId=%s events=%d", turnID, emitted)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeStreamingSSE(w http.ResponseWriter, r *http.Request, envelopes []streaming.Envelope) {
	flusher, _ := w.(http.Flusher)
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	for _, envelope := range envelopes {
		writeStreamingSSEEnvelope(w, envelope, flusher)
	}
}

func writeStreamingSSEEnvelope(w http.ResponseWriter, envelope streaming.Envelope, flusher http.Flusher) {
	event := envelope.SSEEvent()
	log.Printf("assistant http sse_emit streamId=%s eventType=%s seq=%d traceId=%s", envelope.StreamID, envelope.EventType, envelope.Seq, envelope.TraceID)
	if event.ID != "" {
		_, _ = fmt.Fprintf(w, "id: %s\n", event.ID)
	}
	if event.Event != "" {
		_, _ = fmt.Fprintf(w, "event: %s\n", event.Event)
	}
	payload, _ := json.Marshal(event.Data)
	_, _ = fmt.Fprintf(w, "data: %s\n\n", payload)
	if flusher != nil {
		flusher.Flush()
	}
}

func mustStreamingEnvelope(event string, seq uint64, data any) streaming.Envelope {
	envelope, err := streaming.NewEnvelope(event, seq, data)
	if err != nil {
		panic(err)
	}
	return envelope.Normalized()
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		return err
	}
	if len(strings.TrimSpace(string(body))) == 0 {
		return io.EOF
	}
	return json.Unmarshal(body, v)
}

func readJSONObject(r *http.Request) (map[string]any, error) {
	var payload map[string]any
	if err := readJSON(r, &payload); err != nil {
		return nil, err
	}
	return payload, nil
}

func decodeInteractionEvents(payload map[string]any) ([]assistant.InteractionEvent, error) {
	if rawEvents, ok := payload["events"]; ok {
		list, ok := rawEvents.([]any)
		if !ok {
			return nil, fmt.Errorf("events must be an array")
		}
		out := make([]assistant.InteractionEvent, 0, len(list))
		for _, item := range list {
			obj, ok := item.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("events item must be an object")
			}
			encoded, _ := json.Marshal(obj)
			var event assistant.InteractionEvent
			if err := json.Unmarshal(encoded, &event); err != nil {
				return nil, err
			}
			out = append(out, event)
		}
		return out, nil
	}
	encoded, _ := json.Marshal(payload)
	var event assistant.InteractionEvent
	if err := json.Unmarshal(encoded, &event); err != nil {
		return nil, err
	}
	return []assistant.InteractionEvent{event}, nil
}

func decodeScorecards(payload map[string]any) ([]assistant.Scorecard, error) {
	if rawScores, ok := payload["scorecards"]; ok {
		list, ok := rawScores.([]any)
		if !ok {
			return nil, fmt.Errorf("scorecards must be an array")
		}
		out := make([]assistant.Scorecard, 0, len(list))
		for _, item := range list {
			obj, ok := item.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("scorecards item must be an object")
			}
			encoded, _ := json.Marshal(obj)
			var score assistant.Scorecard
			if err := json.Unmarshal(encoded, &score); err != nil {
				return nil, err
			}
			out = append(out, score)
		}
		return out, nil
	}
	encoded, _ := json.Marshal(payload)
	var score assistant.Scorecard
	if err := json.Unmarshal(encoded, &score); err != nil {
		return nil, err
	}
	return []assistant.Scorecard{score}, nil
}

func applyInteractionRequestContext(event *assistant.InteractionEvent, r *http.Request) {
	if strings.TrimSpace(event.UserID) == "" {
		event.UserID = resolveUserID(r)
	}
	if strings.TrimSpace(event.SessionID) == "" {
		event.SessionID = resolveSessionID(r)
	}
	if strings.TrimSpace(event.TraceID) == "" {
		event.TraceID = resolveTraceID(r)
	}
	if strings.TrimSpace(event.PageID) == "" {
		event.PageID = resolvePageID(r)
	}
	if strings.TrimSpace(event.SurfaceID) == "" {
		event.SurfaceID = resolveSurfaceID(r)
	}
	if strings.TrimSpace(event.RouteID) == "" {
		event.RouteID = resolveRouteID(r)
	}
	if strings.TrimSpace(event.OperationID) == "" {
		event.OperationID = resolveOperationID(r)
	}
	if strings.TrimSpace(event.ExperimentBucket) == "" {
		event.ExperimentBucket = resolveExperimentBucket(r)
	}
	if strings.TrimSpace(event.ClientSentAt) == "" {
		event.ClientSentAt = resolveClientSentAt(r)
	}
}

func applyScorecardRequestContext(score *assistant.Scorecard, r *http.Request) {
	if strings.TrimSpace(score.UserID) == "" {
		score.UserID = resolveUserID(r)
	}
	if strings.TrimSpace(score.PageID) == "" {
		score.PageID = resolvePageID(r)
	}
	if strings.TrimSpace(score.SurfaceID) == "" {
		score.SurfaceID = resolveSurfaceID(r)
	}
	if strings.TrimSpace(score.RouteID) == "" {
		score.RouteID = resolveRouteID(r)
	}
	if strings.TrimSpace(score.OperationID) == "" {
		score.OperationID = resolveOperationID(r)
	}
	if strings.TrimSpace(score.ExperimentBucket) == "" {
		score.ExperimentBucket = resolveExperimentBucket(r)
	}
}

func parseLimit(r *http.Request, fallback int) int {
	if fallback <= 0 {
		fallback = 20
	}
	raw := strings.TrimSpace(r.URL.Query().Get("limit"))
	if raw == "" {
		return fallback
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 {
		return fallback
	}
	return limit
}

func resolveUserID(r *http.Request) string {
	if uid := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); uid != "" {
		return uid
	}
	return "anonymous"
}

func resolveSessionID(r *http.Request) string {
	if sessionID := strings.TrimSpace(r.Header.Get("X-Client-Session-Id")); sessionID != "" {
		return sessionID
	}
	return "unknown-session"
}

func resolvePageID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Page-Id"))
}

func resolveSurfaceID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Surface-Id"))
}

func resolveRouteID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Route-Id"))
}

func resolveOperationID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Operation-Id"))
}

func resolveExperimentBucket(r *http.Request) string {
	if bucket := strings.TrimSpace(r.Header.Get("X-Client-Experiment-Bucket")); bucket != "" {
		return bucket
	}
	if bucket := strings.TrimSpace(r.URL.Query().Get("experimentBucket")); bucket != "" {
		return bucket
	}
	return ""
}

func resolveClientSentAt(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Sent-At"))
}

func resolveTraceID(r *http.Request) string {
	if traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id")); traceID != "" {
		return traceID
	}
	return resolveRequestID(r)
}

func resolveRequestID(r *http.Request) string {
	if requestID := strings.TrimSpace(r.Header.Get("X-Request-Id")); requestID != "" {
		return requestID
	}
	return "assistant-request"
}

func buildRunResponseText(query string) string {
	if strings.TrimSpace(query) == "" {
		return "小趣已收到请求，可以继续补充问题以获取完整答案。"
	}
	return "小趣已收到你的问题：" + query + "。当前 assistant-service 已按最终态提供独立 ingress，可继续承接完整对话编排。"
}

func fmtString(value any) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(value))
}
