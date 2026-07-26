package http

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	interactionapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_interaction_event/application"
	preferencefact "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/application"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	scorecardapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_scorecard_fact/application"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
)

type Handler struct {
	service            *application.AssistantService
	preferenceCommands *preferencefact.CommandFacade
	preferenceQueries  *preferencefact.QueryFacade
	interactionEvents  *interactionapplication.Ingestion
	scorecards         *scorecardapplication.Ingestion
	runs               *runapplication.UseCases
	subscriptions      *subscriptionapplication.UseCases
}

type HandlerOption func(*Handler)

func WithPreferenceFacades(
	commands *preferencefact.CommandFacade,
	queries *preferencefact.QueryFacade,
) HandlerOption {
	return func(handler *Handler) {
		handler.preferenceCommands = commands
		handler.preferenceQueries = queries
	}
}

func NewHandler(
	service *application.AssistantService,
	options ...HandlerOption,
) *Handler {
	handler := &Handler{
		service:            service,
		preferenceCommands: preferencefact.NewCommandFacade(nil, nil),
		preferenceQueries:  preferencefact.NewQueryFacade(nil),
		interactionEvents:  interactionapplication.NewIngestion(service),
		scorecards:         scorecardapplication.NewIngestion(service),
		runs:               runapplication.NewUseCases(service),
		subscriptions:      subscriptionapplication.NewUseCases(service),
	}
	for _, option := range options {
		option(handler)
	}
	return handler
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)
	mux.HandleFunc("POST /assistant/learning/events", h.handleReportInteractionEvent)
	mux.HandleFunc("POST /internal/assistant/learning/scorecards", h.handleReportScorecard)
	mux.HandleFunc("POST /assistant/search/xiaoqu", h.handleSearchXiaoqu)
	mux.HandleFunc("POST /assistant/conversations/{conversationId}/runs", h.handleStartRun)
	mux.HandleFunc("GET /assistant/runs/{runId}", h.handleGetRun)
	mux.HandleFunc("GET /assistant/conversations/{conversationId}/turns", h.handleListConversationTurns)
	mux.HandleFunc("POST /assistant/runs/{runId}/cancel", h.handleCancelRun)
	mux.HandleFunc("GET /assistant/runs/{runId}/events", h.handleStreamRunEvents)
	mux.HandleFunc("POST /assistant/page-context", h.handleReportPageContext)
	mux.HandleFunc("GET /assistant/personalization", h.handleGetEntryPersonalization)
	mux.HandleFunc("GET /assistant/suggested-actions", h.handleGetSuggestedActions)
	mux.HandleFunc("GET /assistant/policy", h.handleGetPolicy)
	mux.HandleFunc("GET /assistant/skills", h.handleListSkills)
	mux.HandleFunc("POST /assistant/skills/creation-suggest", h.handleSuggestCreationAssistance)
	mux.HandleFunc("GET /assistant/tasks", h.handleListTasks)
	mux.HandleFunc("GET /assistant/ops/learning-summary", h.handleGetLearningOpsSummary)
	mux.HandleFunc("POST /assistant/preferences", h.handleSetPreference)
	mux.HandleFunc("GET /assistant/preferences", h.handleListPreferences)
	mux.HandleFunc("POST /assistant/preferences/{preferenceId}/revoke", h.handleRevokePreference)
	mux.HandleFunc("POST /assistant/preferences/{preferenceId}/restore", h.handleRestorePreference)
	mux.HandleFunc("GET /assistant/skill-subscriptions", h.handleListSkillSubscriptions)
	mux.HandleFunc("POST /assistant/skill-subscriptions", h.handleCreateSkillSubscription)
	mux.HandleFunc("GET /assistant/skill-subscriptions/{subscriptionId}", h.handleGetSkillSubscription)
	mux.HandleFunc("PATCH /assistant/skill-subscriptions/{subscriptionId}/status", h.handleUpdateSkillSubscriptionStatus)
	mux.HandleFunc("POST /internal/assistant/skill-subscriptions:tick", h.handleTickSkillSubscriptionCron)
	mux.HandleFunc("POST /assistant/intersections/reminders/tick", h.handleTickIntersectionReminders)
	mux.HandleFunc("POST /assistant/skills/{skillId}/consent", h.handleSkillConsentRoutes)
	mux.HandleFunc("DELETE /assistant/skills/{skillId}/consent", h.handleSkillConsentRoutes)
	mux.HandleFunc("GET /assistant/consents", h.handleListConsents)
	mux.HandleFunc("POST /assistant/conversations", h.handleCreateConversation)
	mux.HandleFunc("GET /assistant/conversations", h.handleListConversations)
	mux.HandleFunc("GET /assistant/conversations/{conversationId}", h.handleGetConversation)
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

func (h *Handler) handleGetEntryPersonalization(w http.ResponseWriter, r *http.Request) {
	view, err := h.service.GetEntryPersonalization(r.Context(), resolveUserID(r), strings.TrimSpace(r.URL.Query().Get("pageType")))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
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
	resp, err := h.interactionEvents.Append(r.Context(), events)
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
	resp, err := h.scorecards.Append(r.Context(), scores)
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

type setAssistantPreferenceRequest struct {
	Scope          string `json:"scope"`
	ConversationID string `json:"conversationId"`
	Kind           string `json:"kind"`
	Value          string `json:"value"`
	SourceType     string `json:"sourceType"`
}

func (h *Handler) handleSetPreference(w http.ResponseWriter, r *http.Request) {
	var input setAssistantPreferenceRequest
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(
			w,
			r,
			preferencefact.InvalidArgumentError(err.Error()),
		)
		return
	}
	fact, err := h.preferenceCommands.SetPreference(
		r.Context(),
		preferencefact.SetPreferenceCommand{
			UserID:         resolveUserID(r),
			Scope:          input.Scope,
			ConversationID: input.ConversationID,
			Kind:           input.Kind,
			Value:          input.Value,
			SourceType:     input.SourceType,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, fact)
}

func (h *Handler) handleListPreferences(w http.ResponseWriter, r *http.Request) {
	view, err := h.preferenceQueries.ListPreferences(
		r.Context(),
		preferencefact.ListPreferencesQuery{
			UserID:         resolveUserID(r),
			Scope:          strings.TrimSpace(r.URL.Query().Get("scope")),
			ConversationID: strings.TrimSpace(r.URL.Query().Get("conversationId")),
			Status:         strings.TrimSpace(r.URL.Query().Get("status")),
			Limit:          100,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleRevokePreference(w http.ResponseWriter, r *http.Request) {
	fact, err := h.preferenceCommands.RevokePreference(
		r.Context(),
		resolveUserID(r),
		r.PathValue("preferenceId"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, fact)
}

func (h *Handler) handleRestorePreference(w http.ResponseWriter, r *http.Request) {
	fact, err := h.preferenceCommands.RestorePreference(
		r.Context(),
		resolveUserID(r),
		r.PathValue("preferenceId"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, fact)
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

func (h *Handler) handleSuggestCreationAssistance(w http.ResponseWriter, r *http.Request) {
	var input assistant.AssistantCreationSuggestRequest
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	view, err := h.service.SuggestCreationAssistance(r.Context(), resolveUserID(r), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleListSkillSubscriptions(w http.ResponseWriter, r *http.Request) {
	view, err := h.subscriptions.List(
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
	input.CreatedByPersonaID = resolvePersonaID(r)
	subscription, err := h.subscriptions.Create(r.Context(), resolveUserID(r), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, subscription)
}

func (h *Handler) handleGetSkillSubscription(w http.ResponseWriter, r *http.Request) {
	subscription, err := h.subscriptions.Get(r.Context(), resolveUserID(r), r.PathValue("subscriptionId"))
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
	subscription, err := h.subscriptions.UpdateStatus(r.Context(), resolveUserID(r), r.PathValue("subscriptionId"), input)
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
	result, err := h.subscriptions.Tick(r.Context(), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleTickIntersectionReminders(w http.ResponseWriter, r *http.Request) {
	var input application.IntersectionReminderTickInput
	if err := readJSON(r, &input); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	if strings.TrimSpace(input.UserID) == "" {
		input.UserID = resolveUserID(r)
	}
	result, err := h.service.TickIntersectionReminders(r.Context(), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleListConsents(w http.ResponseWriter, r *http.Request) {
	accountID, err := requireVerifiedAccount(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items, err := h.service.ListConsents(r.Context(), accountID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *Handler) handleSkillConsentRoutes(w http.ResponseWriter, r *http.Request) {
	accountID, err := requireVerifiedAccount(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/assistant/skills/")
	parts := strings.Split(path, "/")
	if len(parts) != 2 || parts[1] != "consent" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "无效路径", "expected /assistant/skills/{skillId}/consent"))
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
		consent, err := h.service.GrantSkillConsent(r.Context(), accountID, skillID, strings.TrimSpace(body.GrantedScope))
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"consent": consent})
	case http.MethodDelete:
		if err := h.service.RevokeSkillConsent(r.Context(), accountID, skillID); err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "skillId": skillID})
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "方法不支持", "only POST/DELETE"))
	}
}

func requireVerifiedAccount(r *http.Request) (string, error) {
	claims, ok := rtauth.PrincipalFromContext(r.Context())
	if ok && strings.TrimSpace(claims.Subject) != "" {
		return strings.TrimSpace(claims.Subject), nil
	}
	return "", rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "unauthorized"),
		"请先登录",
		"assistant consent requires a verified account principal",
	).WithRecovery("surface", 0)
}

// requireIdentifiedUser 供 conversation/run 读写路径使用：身份来自 JWT principal
// 或 auth middleware 白名单化后的可信 identity header，二者皆空时拒绝，
// 不再回退 anonymous（metadata 声明 auth_mode: required + actor persona）。
func requireIdentifiedUser(r *http.Request) (string, error) {
	if claims, ok := rtauth.PrincipalFromContext(r.Context()); ok && strings.TrimSpace(claims.Subject) != "" {
		return strings.TrimSpace(claims.Subject), nil
	}
	if uid := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); uid != "" {
		return uid, nil
	}
	return "", rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "unauthorized"),
		"请先登录",
		"assistant conversation/run requires an identified persona",
	).WithRecovery("surface", 0)
}

// requireCanonicalCommandIdentity enforces the one stable mutation identity
// declared by assistant command metadata. The body identifies the aggregate
// replay key; the HTTP header lets middleware, traces, and retrying transports
// observe the same key. Accepting either one alone would create two divergent
// idempotency paths.
func requireCanonicalCommandIdentity(
	r *http.Request,
	clientRequestID string,
) (string, error) {
	bodyID := strings.TrimSpace(clientRequestID)
	if bodyID == "" {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"clientRequestId 不能为空",
			"missing clientRequestId",
		)
	}
	headerID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if headerID == "" {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"幂等请求头不能为空",
			"missing Idempotency-Key",
		)
	}
	if headerID != bodyID {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"幂等身份不一致",
			"clientRequestId does not match Idempotency-Key",
		)
	}
	return bodyID, nil
}

// requireRunCommandIdentity preserves the operation-specific failure contract.
// Conversation creation has its own error surface, while StartAssistantRun
// declares ASSISTANT.USER.run_invalid_argument for every malformed command
// identity variant.
func requireRunCommandIdentity(
	r *http.Request,
	clientRequestID string,
) (string, error) {
	requestID, err := requireCanonicalCommandIdentity(r, clientRequestID)
	if err != nil {
		return "", application.AssistantRunInvalidArgument(err.Error())
	}
	return requestID, nil
}

func (h *Handler) handleCreateConversation(w http.ResponseWriter, r *http.Request) {
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input assistant.CreateConversationInput
	if err := readJSON(r, &input); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	input.ClientRequestID, err = requireCanonicalCommandIdentity(
		r,
		input.ClientRequestID,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	conversation, err := h.service.CreateConversation(r.Context(), userID, input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, conversation)
}

func (h *Handler) handleGetConversation(w http.ResponseWriter, r *http.Request) {
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	conversation, err := h.service.GetConversation(r.Context(), userID, r.PathValue("conversationId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, conversation)
}

func (h *Handler) handleStartRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input assistant.CreateTurnInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, application.AssistantRunInvalidArgument(err.Error()))
		return
	}
	applyRunRequestContext(&input, r)
	input.ClientRequestID, err = requireRunCommandIdentity(
		r,
		input.ClientRequestID,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	turn, err := h.runs.Start(r.Context(), userID, r.PathValue("conversationId"), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	log.Printf("assistant http start_run conversationId=%s runId=%s traceId=%s", turn.ConversationID, turn.TurnID, turn.TraceID)
	writeJSON(w, http.StatusCreated, application.ProjectAssistantTurnEnvelope(turn))
}

func (h *Handler) handleGetRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := h.runs.Get(r.Context(), userID, r.PathValue("runId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, application.ProjectAssistantTurnEnvelope(run))
}

func (h *Handler) handleListConversations(w http.ResponseWriter, r *http.Request) {
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	view, err := h.service.ListConversations(
		r.Context(),
		userID,
		parseLimit(r, 20),
		r.URL.Query().Get("cursor"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleListConversationTurns(w http.ResponseWriter, r *http.Request) {
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	view, err := h.runs.ListTurns(
		r.Context(),
		userID,
		r.PathValue("conversationId"),
		parseLimit(r, 20),
		r.URL.Query().Get("cursor"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleCancelRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := h.runs.Cancel(r.Context(), userID, r.PathValue("runId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	log.Printf("assistant http cancel_run runId=%s status=%s", run.TurnID, run.Status)
	writeJSON(w, http.StatusOK, application.ProjectAssistantTurnEnvelope(run))
}

func (h *Handler) handleStreamRunEvents(w http.ResponseWriter, r *http.Request) {
	runID := r.PathValue("runId")
	userID, err := requireIdentifiedUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	afterSeq, err := runResumeAfterSeq(r, runID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	turn, err := h.service.GetTurn(r.Context(), userID, runID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	log.Printf(
		"assistant http stream_run_events_requested runId=%s afterSeq=%d requestId=%s traceId=%s",
		runID,
		afterSeq,
		resolveRequestID(r),
		resolveTraceID(r),
	)
	flusher, _ := w.(http.Flusher)
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	emitted := 0
	err = h.service.StreamTurnAfterSeq(r.Context(), userID, runID, afterSeq, func(envelope streaming.Envelope) error {
		emitted++
		writeStreamingSSEEnvelope(w, envelope, flusher)
		return nil
	})
	if err != nil {
		log.Printf("assistant http stream_run_events_failed runId=%s emitted=%d err=%v", runID, emitted, err)
		// SSE 头已写出，无法改状态码；以结构化终止事件把错误码交给客户端。
		errorCode := "ASSISTANT.SYSTEM.stream_unavailable"
		var appErr *rterr.AppError
		if errors.As(err, &appErr) {
			errorCode = appErr.Code.String()
		}
		writeStreamingSSEEnvelope(w, streaming.Envelope{
			EventID:   runID + ":error",
			StreamID:  runID,
			EventType: string(application.AssistantStreamEventFailed),
			Seq:       afterSeq + uint64(emitted) + 1,
			TraceID:   turn.TraceID,
			Payload: map[string]any{
				"conversationId": turn.ConversationID,
				"turnId":         runID,
				"code":           errorCode,
			},
		}, flusher)
		return
	}
	log.Printf("assistant http stream_run_events_ready runId=%s events=%d", runID, emitted)
}

func runResumeAfterSeq(r *http.Request, runID string) (uint64, error) {
	token := strings.TrimSpace(r.Header.Get("Last-Event-ID"))
	if token == "" {
		token = strings.TrimSpace(r.URL.Query().Get("resumeToken"))
	}
	if token == "" {
		return 0, nil
	}
	streamID, seq, err := streaming.ParseResumeToken(token)
	if err != nil || streamID != strings.TrimSpace(runID) {
		return 0, application.AssistantRunInvalidArgument("invalid assistant stream resume token")
	}
	return seq, nil
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
	normalized := envelope.Normalized()
	data := map[string]any{
		"schema":         "assistant_stream_event",
		"eventId":        normalized.EventID,
		"conversationId": streamPayloadString(normalized.Payload, "conversationId"),
		"turnId":         streamPayloadString(normalized.Payload, "turnId"),
		"seq":            normalized.Seq,
		"eventType":      normalized.EventType,
		"traceId":        normalized.TraceID,
		"payload":        normalized.Payload,
		"createdAt":      normalized.CreatedAt.Format(time.RFC3339Nano),
	}
	if normalized.RuntimeFailure != nil {
		data["runtimeFailure"] = normalized.RuntimeFailure
	}
	payload, _ := json.Marshal(data)
	_, _ = fmt.Fprintf(w, "data: %s\n\n", payload)
	if flusher != nil {
		flusher.Flush()
	}
}

func streamPayloadString(payload map[string]any, key string) string {
	value, _ := payload[key].(string)
	return strings.TrimSpace(value)
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
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
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

func applyRunRequestContext(input *assistant.CreateTurnInput, r *http.Request) {
	if input == nil {
		return
	}
	input.RequestContext = assistant.AssistantRunRequestContext{
		SessionID:   resolveSessionID(r),
		PageID:      resolvePageID(r),
		SurfaceID:   resolveSurfaceID(r),
		RouteID:     resolveRouteID(r),
		OperationID: resolveOperationID(r),
		TraceID:     resolveTraceID(r),
	}.Normalized()
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

func resolvePersonaID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id"))
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
