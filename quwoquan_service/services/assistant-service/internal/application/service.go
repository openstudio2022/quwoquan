package application

import (
	"context"
	"crypto/sha1"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	messaging "quwoquan_service/runtime/messaging"
	rtobs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	preferencemodel "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/model"
)

const pageContextTTL = 5 * time.Minute

type EventStore interface {
	InsertInteractionEvent(ctx context.Context, event assistant.InteractionEvent) error
	InsertScorecard(ctx context.Context, score assistant.Scorecard) error
	ListLatestInteractionEvents(ctx context.Context, userID string, limit int) ([]assistant.InteractionEvent, error)
	ListLatestScorecards(ctx context.Context, userID string, limit int) ([]assistant.Scorecard, error)
}

type LearningProfileStore interface {
	ProjectInteractionEvent(ctx context.Context, event assistant.InteractionEvent, priority string) error
	ProjectScorecard(ctx context.Context, score assistant.Scorecard, priority string) error
	GetLearningProfile(ctx context.Context, userID string) (*assistant.AssistantLearningProfile, error)
	BuildTaskItems(ctx context.Context, userID string, now time.Time) ([]assistant.AssistantUserTaskView, error)
}

type ConsentStore interface {
	ListActiveConsents(ctx context.Context, userID string) ([]assistant.SkillConsent, error)
	UpsertConsent(ctx context.Context, consent assistant.SkillConsent) (assistant.SkillConsent, error)
	RevokeConsent(ctx context.Context, userID string, skillID string, revokedAt time.Time) error
}

type Projector interface {
	Project(ctx context.Context, event ProjectorEvent) error
}

type ProjectorEvent struct {
	Type          string         `json:"type"`
	AggregateType string         `json:"aggregateType"`
	AggregateID   string         `json:"aggregateId"`
	Payload       map[string]any `json:"payload"`
	OccurredAt    time.Time      `json:"occurredAt"`
}

type PreferenceSnapshotReader interface {
	ResolveActiveSnapshots(
		ctx context.Context,
		userID string,
		conversationID string,
	) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error)
}

// IntersectionEvidenceReader 是 assistant 对 content 公开对象 Reader 的专属 port。
// 它必须以调用 actor 授权读取当前事实，而不能信任客户端交集卡的展示内容。
type IntersectionEvidenceReader interface {
	ResolveAuthorizedIntersectionEvidence(
		ctx context.Context,
		personaID string,
		refs []assistant.AssistantIntersectionEvidenceRef,
	) ([]assistant.AuthorizedIntersectionEvidence, error)
}

type AssistantService struct {
	events                     EventStore
	profiles                   LearningProfileStore
	consents                   ConsentStore
	cache                      rtredis.Client
	publisher                  messaging.EventPublisher
	projector                  Projector
	notificationMessages       NotificationAppMessageCommandWriter
	subscriptions              SkillSubscriptionStore
	proactiveInterest          ProactiveInterestReader
	creationGrounding          CreationSuggestGrounding
	xiaoquSearch               XiaoquSearchReader
	intersectionInbox          IntersectionInboxReader
	intersectionEvidence       IntersectionEvidenceReader
	chatGrounding              ChatGroundingClient
	agentLoop                  *AgentLoop
	conversationRuns           ConversationRunStore
	preferenceSnapshots        PreferenceSnapshotReader
	runEvents                  AssistantRunEventStore
	runCancels                 *runCancelRegistry
	runExecutions              *runExecutionRegistry
	intersectionReminderPolicy IntersectionReminderPolicy
	now                        func() time.Time
}

type AssistantServiceOption func(*AssistantService)

func WithEventPublisher(pub messaging.EventPublisher) AssistantServiceOption {
	return func(s *AssistantService) { s.publisher = pub }
}

func WithProjector(p Projector) AssistantServiceOption {
	return func(s *AssistantService) { s.projector = p }
}

func WithLearningProfileStore(store LearningProfileStore) AssistantServiceOption {
	return func(s *AssistantService) { s.profiles = store }
}

func WithAgentLoop(loop *AgentLoop) AssistantServiceOption {
	return func(s *AssistantService) { s.agentLoop = loop }
}

func WithPreferenceSnapshotReader(reader PreferenceSnapshotReader) AssistantServiceOption {
	return func(s *AssistantService) { s.preferenceSnapshots = reader }
}

func WithSkillSubscriptionStore(store SkillSubscriptionStore) AssistantServiceOption {
	return func(s *AssistantService) { s.subscriptions = store }
}

// WithProactiveInterestReader injects the user-domain interest profile reader
// used to personalize proactive (cron) skill output. When unset, proactive
// output degrades to non-personalized copy.
func WithProactiveInterestReader(reader ProactiveInterestReader) AssistantServiceOption {
	return func(s *AssistantService) { s.proactiveInterest = reader }
}

func WithCreationSuggestGrounding(grounding CreationSuggestGrounding) AssistantServiceOption {
	return func(s *AssistantService) { s.creationGrounding = grounding }
}

func WithIntersectionInboxReader(reader IntersectionInboxReader) AssistantServiceOption {
	return func(s *AssistantService) { s.intersectionInbox = reader }
}

func WithIntersectionEvidenceReader(reader IntersectionEvidenceReader) AssistantServiceOption {
	return func(s *AssistantService) { s.intersectionEvidence = reader }
}

func WithIntersectionReminderPolicy(policy IntersectionReminderPolicy) AssistantServiceOption {
	return func(s *AssistantService) {
		s.intersectionReminderPolicy = normalizeIntersectionReminderPolicy(policy)
	}
}

func NewAssistantService(events EventStore, consents ConsentStore, cache rtredis.Client, opts ...AssistantServiceOption) *AssistantService {
	svc := &AssistantService{
		events:                     events,
		consents:                   consents,
		cache:                      cache,
		runCancels:                 newRunCancelRegistry(),
		runExecutions:              newRunExecutionRegistry(),
		intersectionReminderPolicy: defaultIntersectionReminderPolicy(),
		now: func() time.Time {
			return time.Now().UTC()
		},
	}
	for _, opt := range opts {
		opt(svc)
	}
	if svc.agentLoop == nil {
		svc.agentLoop = NewAgentLoop(nil, ReactRuntime{}, svc.now)
	}
	return svc
}

func (s *AssistantService) ReportInteractionEvent(ctx context.Context, event assistant.InteractionEvent) (map[string]any, error) {
	return s.ReportInteractionEvents(ctx, []assistant.InteractionEvent{event})
}

func (s *AssistantService) ReportInteractionEvents(ctx context.Context, events []assistant.InteractionEvent) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ReportInteractionEvents",
		attribute.Int("batch.count", len(events)))
	defer func() { rtobs.EndSpan(span, err) }()

	if len(events) == 0 {
		return nil, rterr.NewInvalidArgument(rterr.ModuleAssistant, "events 不能为空", "empty interaction events")
	}
	acceptedIDs := make([]string, 0, len(events))
	priorityDist := map[string]int{}
	feedbackTypeDist := map[string]int{}
	for _, raw := range events {
		event, priority, err := s.normalizeInteractionEvent(raw)
		if err != nil {
			return nil, err
		}
		claimed, err := s.claimLearningDedup(ctx, "event", event.EventID, event.CreatedAt)
		if err != nil {
			return nil, err
		}
		if !claimed {
			acceptedIDs = append(acceptedIDs, event.EventID)
			continue
		}
		if err := s.storeInteractionEvent(ctx, event); err != nil {
			s.releaseLearningDedup(ctx, "event", event.EventID)
			return nil, err
		}
		s.writeInteractionHotPath(ctx, event, priority)
		if err := s.projectLearningInteraction(ctx, event, priority); err != nil {
			s.releaseLearningDedup(ctx, "event", event.EventID)
			return nil, err
		}
		s.publishInteractionEvent(ctx, event)
		acceptedIDs = append(acceptedIDs, event.EventID)
		priorityDist[priority]++
		if feedbackType := strings.TrimSpace(event.FeedbackType); feedbackType != "" {
			feedbackTypeDist[feedbackType]++
		}
	}
	return map[string]any{
		"accepted":                 len(acceptedIDs) == len(events),
		"acceptedCount":            len(acceptedIDs),
		"count":                    len(events),
		"acceptedIds":              acceptedIDs,
		"status":                   "ok",
		"resource":                 "interaction_event_batch",
		"priorityDistribution":     priorityDist,
		"feedbackTypeDistribution": feedbackTypeDist,
		"storedAt":                 s.now().Format(time.RFC3339),
	}, nil
}

func (s *AssistantService) ReportScorecard(ctx context.Context, score assistant.Scorecard) (map[string]any, error) {
	return s.ReportScorecards(ctx, []assistant.Scorecard{score})
}

func (s *AssistantService) ReportScorecards(ctx context.Context, scores []assistant.Scorecard) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ReportScorecards",
		attribute.Int("batch.count", len(scores)))
	defer func() { rtobs.EndSpan(span, err) }()

	if len(scores) == 0 {
		return nil, rterr.NewInvalidArgument(rterr.ModuleAssistant, "scorecards 不能为空", "empty scorecards")
	}
	acceptedIDs := make([]string, 0, len(scores))
	metricDist := map[string]int{}
	priorityDist := map[string]int{}
	for _, raw := range scores {
		score, priority, err := s.normalizeScorecard(raw)
		if err != nil {
			return nil, err
		}
		claimed, err := s.claimLearningDedup(ctx, "scorecard", score.ScoreID, score.CreatedAt)
		if err != nil {
			return nil, err
		}
		if !claimed {
			acceptedIDs = append(acceptedIDs, score.ScoreID)
			continue
		}
		if err := s.storeScorecard(ctx, score); err != nil {
			s.releaseLearningDedup(ctx, "scorecard", score.ScoreID)
			return nil, err
		}
		s.writeScorecardHotPath(ctx, score, priority)
		if err := s.projectLearningScorecard(ctx, score, priority); err != nil {
			s.releaseLearningDedup(ctx, "scorecard", score.ScoreID)
			return nil, err
		}
		s.publishScorecardEvent(ctx, score)
		acceptedIDs = append(acceptedIDs, score.ScoreID)
		metricDist[score.MetricID]++
		priorityDist[priority]++
	}
	return map[string]any{
		"accepted":             len(acceptedIDs) == len(scores),
		"acceptedCount":        len(acceptedIDs),
		"count":                len(scores),
		"acceptedIds":          acceptedIDs,
		"status":               "ok",
		"resource":             "scorecard_batch",
		"metricDistribution":   metricDist,
		"priorityDistribution": priorityDist,
		"storedAt":             s.now().Format(time.RFC3339),
	}, nil
}

func (s *AssistantService) normalizeInteractionEvent(event assistant.InteractionEvent) (assistant.InteractionEvent, string, error) {
	if strings.TrimSpace(event.EventID) == "" {
		return assistant.InteractionEvent{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "eventId 不能为空", "missing eventId")
	}
	if strings.TrimSpace(event.RunID) == "" {
		return assistant.InteractionEvent{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "runId 不能为空", "missing runId")
	}
	if strings.TrimSpace(event.UserID) == "" {
		return assistant.InteractionEvent{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if strings.TrimSpace(event.SessionID) == "" {
		return assistant.InteractionEvent{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "sessionId 不能为空", "missing sessionId")
	}
	if strings.TrimSpace(event.PageType) == "" {
		event.PageType = "assistant_dialog"
	}
	if strings.TrimSpace(event.DomainID) == "" {
		event.DomainID = "general"
	}
	event.EventType = normalizeInteractionEventType(event)
	event.FeedbackType = normalizeFeedbackType(event)
	event.ExplicitThumb = normalizeExplicitThumb(event.ExplicitThumb)
	event.UserTags = sanitizeStringList(event.UserTags)
	event.ExplicitReasonCodes = sanitizeStringList(event.ExplicitReasonCodes)
	event.QueryText = strings.TrimSpace(event.QueryText)
	event.AnswerText = strings.TrimSpace(event.AnswerText)
	event.CorrectionText = strings.TrimSpace(event.CorrectionText)
	event.FeedbackText = strings.TrimSpace(firstNonEmpty(event.FeedbackText, event.CorrectionText))
	if event.DurationMs < 0 {
		event.DurationMs = 0
	}
	if event.CreatedAt.IsZero() {
		event.CreatedAt = s.now()
	} else {
		event.CreatedAt = event.CreatedAt.UTC()
	}
	event.FeedbackScore = deriveFeedbackScore(event)
	return event, classifyInteractionPriority(event), nil
}

func (s *AssistantService) normalizeScorecard(score assistant.Scorecard) (assistant.Scorecard, string, error) {
	if strings.TrimSpace(score.ScoreID) == "" {
		return assistant.Scorecard{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "scoreId 不能为空", "missing scoreId")
	}
	if strings.TrimSpace(score.EventID) == "" {
		return assistant.Scorecard{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "eventId 不能为空", "missing eventId")
	}
	if strings.TrimSpace(score.UserID) == "" {
		return assistant.Scorecard{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if strings.TrimSpace(score.DomainID) == "" {
		score.DomainID = "general"
	}
	score.MetricID = strings.TrimSpace(score.MetricID)
	if score.MetricID == "" {
		return assistant.Scorecard{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "metricId 不能为空", "missing metricId")
	}
	if strings.TrimSpace(score.ScoreSource) == "" {
		score.ScoreSource = "implicit"
	}
	if score.ScoreValue < 0 || score.ScoreValue > 5 {
		return assistant.Scorecard{}, "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "scoreValue 超出范围", fmt.Sprintf("invalid scoreValue %.3f", score.ScoreValue))
	}
	if score.CreatedAt.IsZero() {
		score.CreatedAt = s.now()
	} else {
		score.CreatedAt = score.CreatedAt.UTC()
	}
	return score, classifyScorecardPriority(score), nil
}

func (s *AssistantService) claimLearningDedup(ctx context.Context, kind string, id string, createdAt time.Time) (bool, error) {
	if s.cache == nil {
		return true, nil
	}
	key := fmt.Sprintf("assistant:learning:dedup:%s:%s", strings.TrimSpace(kind), strings.TrimSpace(id))
	ok, err := s.cache.SetNX(ctx, key, createdAt.Format(time.RFC3339), 7*24*time.Hour)
	if err != nil {
		return false, rterr.NewUnavailable(rterr.ModuleAssistant, "学习事件幂等校验失败", err.Error())
	}
	return ok, nil
}

func (s *AssistantService) releaseLearningDedup(ctx context.Context, kind string, id string) {
	if s.cache == nil {
		return
	}
	key := fmt.Sprintf("assistant:learning:dedup:%s:%s", strings.TrimSpace(kind), strings.TrimSpace(id))
	_ = s.cache.Del(ctx, key)
}

func (s *AssistantService) storeInteractionEvent(ctx context.Context, event assistant.InteractionEvent) error {
	if s.events == nil {
		return nil
	}
	return s.events.InsertInteractionEvent(ctx, event)
}

func (s *AssistantService) storeScorecard(ctx context.Context, score assistant.Scorecard) error {
	if s.events == nil {
		return nil
	}
	return s.events.InsertScorecard(ctx, score)
}

func (s *AssistantService) projectLearningInteraction(ctx context.Context, event assistant.InteractionEvent, priority string) error {
	if s.profiles != nil {
		if err := s.profiles.ProjectInteractionEvent(ctx, event, priority); err != nil {
			return err
		}
	}
	if s.projector == nil {
		return nil
	}
	return s.projector.Project(ctx, ProjectorEvent{
		Type:          interactionEventTypeForPublish(event),
		AggregateType: "AssistantRun",
		AggregateID:   event.RunID,
		Payload:       interactionEventPayload(event, priority),
		OccurredAt:    event.CreatedAt,
	})
}

func (s *AssistantService) projectLearningScorecard(ctx context.Context, score assistant.Scorecard, priority string) error {
	if s.profiles != nil {
		if err := s.profiles.ProjectScorecard(ctx, score, priority); err != nil {
			return err
		}
	}
	if s.projector == nil {
		return nil
	}
	return s.projector.Project(ctx, ProjectorEvent{
		Type:          "AssistantScorecardReported",
		AggregateType: "AssistantRun",
		AggregateID:   firstNonEmpty(score.RunID, score.EventID, score.ScoreID),
		Payload:       scorecardPayload(score, priority),
		OccurredAt:    score.CreatedAt,
	})
}

func (s *AssistantService) publishInteractionEvent(ctx context.Context, event assistant.InteractionEvent) {
	if s.publisher == nil {
		return
	}
	_ = s.publisher.Publish(ctx, messaging.DomainEvent{
		Type:          interactionEventTypeForPublish(event),
		AggregateType: "AssistantRun",
		AggregateID:   event.RunID,
		Payload:       interactionEventPayload(event, classifyInteractionPriority(event)),
		OccurredAt:    event.CreatedAt.Format(time.RFC3339),
	})
}

func (s *AssistantService) publishScorecardEvent(ctx context.Context, score assistant.Scorecard) {
	if s.publisher == nil {
		return
	}
	_ = s.publisher.Publish(ctx, messaging.DomainEvent{
		Type:          "AssistantScorecardReported",
		AggregateType: "AssistantRun",
		AggregateID:   firstNonEmpty(score.RunID, score.EventID, score.ScoreID),
		Payload:       scorecardPayload(score, classifyScorecardPriority(score)),
		OccurredAt:    score.CreatedAt.Format(time.RFC3339),
	})
}

func interactionEventTypeForPublish(event assistant.InteractionEvent) string {
	if strings.TrimSpace(event.FeedbackType) != "" || event.FeedbackScore != 0 || strings.TrimSpace(event.FeedbackText) != "" {
		return "AssistantFeedbackReceived"
	}
	return "AssistantInteractionRecorded"
}

func interactionEventPayload(event assistant.InteractionEvent, priority string) map[string]any {
	return map[string]any{
		"eventId":             event.EventID,
		"runId":               event.RunID,
		"traceId":             event.TraceID,
		"userId":              event.UserID,
		"sessionId":           event.SessionID,
		"pageType":            event.PageType,
		"domainId":            event.DomainID,
		"pageId":              event.PageID,
		"surfaceId":           event.SurfaceID,
		"routeId":             event.RouteID,
		"operationId":         event.OperationID,
		"experimentBucket":    event.ExperimentBucket,
		"eventType":           event.EventType,
		"feedbackType":        event.FeedbackType,
		"feedbackScore":       event.FeedbackScore,
		"feedbackText":        event.FeedbackText,
		"explicitThumb":       event.ExplicitThumb,
		"explicitReasonCodes": append([]string(nil), event.ExplicitReasonCodes...),
		"priority":            priority,
		"queryTextDigest":     digestText(event.QueryText),
		"answerTextDigest":    digestText(event.AnswerText),
		"createdAt":           event.CreatedAt.Format(time.RFC3339),
		"copiedAnswer":        event.CopiedAnswer,
		"sharedAnswer":        event.SharedAnswer,
		"regeneratedAnswer":   event.RegeneratedAnswer,
		"styleAdjusted":       event.StyleAdjusted,
		"modelSwitched":       event.ModelSwitched,
		"referenceOpened":     event.ReferenceOpened,
	}
}

func scorecardPayload(score assistant.Scorecard, priority string) map[string]any {
	return map[string]any{
		"scoreId":          score.ScoreID,
		"eventId":          score.EventID,
		"runId":            score.RunID,
		"userId":           score.UserID,
		"domainId":         score.DomainID,
		"pageId":           score.PageID,
		"surfaceId":        score.SurfaceID,
		"routeId":          score.RouteID,
		"operationId":      score.OperationID,
		"experimentBucket": score.ExperimentBucket,
		"metricId":         score.MetricID,
		"scoreValue":       score.ScoreValue,
		"scoreSource":      score.ScoreSource,
		"priority":         priority,
		"createdAt":        score.CreatedAt.Format(time.RFC3339),
	}
}

func (s *AssistantService) writeInteractionHotPath(ctx context.Context, event assistant.InteractionEvent, priority string) {
	if s.cache == nil {
		return
	}
	key := fmt.Sprintf("assistant:learning:event:%s:%s", fallbackUser(event.UserID), event.EventID)
	_ = s.cache.HSet(ctx, key, "runId", event.RunID)
	_ = s.cache.HSet(ctx, key, "domainId", event.DomainID)
	_ = s.cache.HSet(ctx, key, "pageType", event.PageType)
	_ = s.cache.HSet(ctx, key, "eventType", event.EventType)
	_ = s.cache.HSet(ctx, key, "feedbackType", event.FeedbackType)
	_ = s.cache.HSet(ctx, key, "feedbackScore", formatFloat(event.FeedbackScore))
	_ = s.cache.HSet(ctx, key, "priority", priority)
	_ = s.cache.HSet(ctx, key, "queryTextDigest", digestText(event.QueryText))
	_ = s.cache.HSet(ctx, key, "answerTextDigest", digestText(event.AnswerText))
	_ = s.cache.HSet(ctx, key, "updatedAt", event.CreatedAt.Format(time.RFC3339))
	_ = s.cache.Expire(ctx, key, 24*time.Hour)
}

func (s *AssistantService) writeScorecardHotPath(ctx context.Context, score assistant.Scorecard, priority string) {
	if s.cache == nil {
		return
	}
	cacheKey := fmt.Sprintf("rec:assistant_score:%s:%s", score.UserID, score.MetricID)
	_ = s.cache.HSet(ctx, cacheKey, "domainId", score.DomainID)
	_ = s.cache.HSet(ctx, cacheKey, "scoreSource", score.ScoreSource)
	_ = s.cache.HSet(ctx, cacheKey, "priority", priority)
	_ = s.cache.HSet(ctx, cacheKey, "updatedAt", score.CreatedAt.Format(time.RFC3339))
	_ = s.cache.HIncrByFloat(ctx, cacheKey, "scoreValue", score.ScoreValue)
	_ = s.cache.HIncrByFloat(ctx, cacheKey, "sampleCount", 1)
	_ = s.cache.Expire(ctx, cacheKey, 24*time.Hour)
}

func normalizeInteractionEventType(event assistant.InteractionEvent) string {
	existing := strings.TrimSpace(event.EventType)
	switch existing {
	case "query", "response", "feedback", "action_click", "skill_trigger", "tool_call", "error":
		return existing
	}
	if normalizeFeedbackType(event) != "" {
		return "feedback"
	}
	if event.ReferenceOpened || event.CopiedAnswer || event.SharedAnswer || event.RegeneratedAnswer || event.StyleAdjusted || event.ModelSwitched {
		return "action_click"
	}
	return "response"
}

func normalizeFeedbackType(event assistant.InteractionEvent) string {
	existing := strings.TrimSpace(event.FeedbackType)
	switch existing {
	case "thumbs_up", "thumbs_down", "rating", "text":
		return existing
	}
	switch normalizeExplicitThumb(event.ExplicitThumb) {
	case "up":
		return "thumbs_up"
	case "down":
		return "thumbs_down"
	}
	if strings.TrimSpace(event.CorrectionText) != "" || strings.TrimSpace(event.FeedbackText) != "" {
		return "text"
	}
	return ""
}

func normalizeExplicitThumb(raw string) string {
	normalized := strings.TrimSpace(strings.ToLower(raw))
	switch normalized {
	case "up", "thumbs_up", "like", "positive":
		return "up"
	case "down", "thumbs_down", "dislike", "negative":
		return "down"
	default:
		return "none"
	}
}

func deriveFeedbackScore(event assistant.InteractionEvent) float64 {
	if event.FeedbackScore > 0 {
		return event.FeedbackScore
	}
	switch normalizeFeedbackType(event) {
	case "thumbs_up":
		return 1
	case "thumbs_down":
		return -1
	case "text":
		return 0.2
	default:
		return 0
	}
}

func classifyInteractionPriority(event assistant.InteractionEvent) string {
	if event.FeedbackType == "thumbs_down" || event.FeedbackType == "text" || containsAny(event.ExplicitReasonCodes, "unsafe", "privacy") {
		return "high"
	}
	if event.ReferenceOpened || event.SharedAnswer || event.CopiedAnswer || event.RegeneratedAnswer || event.ModelSwitched || event.StyleAdjusted {
		return "medium"
	}
	return "normal"
}

func classifyScorecardPriority(score assistant.Scorecard) string {
	if score.MetricID == "safety_compliance" || score.MetricID == "privacy_comfort" || score.ScoreValue <= 2 {
		return "high"
	}
	if score.ScoreValue <= 3 {
		return "medium"
	}
	return "normal"
}

func sanitizeStringList(items []string) []string {
	out := make([]string, 0, len(items))
	seen := map[string]struct{}{}
	for _, item := range items {
		trimmed := strings.TrimSpace(item)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
	}
	return out
}

func containsAny(items []string, targets ...string) bool {
	set := map[string]struct{}{}
	for _, item := range items {
		set[strings.TrimSpace(item)] = struct{}{}
	}
	for _, target := range targets {
		if _, ok := set[target]; ok {
			return true
		}
	}
	return false
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func digestText(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}
	sum := sha1.Sum([]byte(trimmed))
	return hex.EncodeToString(sum[:])
}

func formatFloat(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func buildSuggestedActions(pageType string, objectID string) []assistant.SuggestedAction {
	base := []assistant.SuggestedAction{
		{ActionID: "assistant.ask_followup", Type: "open_assistant", Label: "继续追问小趣", Icon: "sparkles", Payload: map[string]any{"pageType": pageType, "objectId": objectID}},
	}
	switch strings.TrimSpace(pageType) {
	case "article_detail", "content_detail":
		return append(base,
			assistant.SuggestedAction{ActionID: "assistant.summarize_article", Type: "summarize", Label: "总结这篇内容", Icon: "article", Payload: map[string]any{"objectId": objectID}},
			assistant.SuggestedAction{ActionID: "assistant.extract_entities", Type: "extract_entities", Label: "提取关键实体", Icon: "label", Payload: map[string]any{"objectId": objectID}},
		)
	case "chat", "assistant_dialog":
		return append(base,
			assistant.SuggestedAction{ActionID: "assistant.review_feedback", Type: "review_feedback", Label: "查看反馈摘要", Icon: "thumb_up", Payload: map[string]any{"scope": "latest"}},
		)
	default:
		return append(base,
			assistant.SuggestedAction{ActionID: "assistant.explain_page", Type: "explain_page", Label: "解释当前页面", Icon: "help", Payload: map[string]any{"pageType": pageType}},
		)
	}
}

func encodeSuggestedActionCache(items []assistant.SuggestedAction) string {
	parts := make([]string, 0, len(items))
	for _, item := range items {
		parts = append(parts, strings.Join([]string{item.ActionID, item.Type, item.Label, item.Icon}, "|"))
	}
	return strings.Join(parts, "\n")
}

func parseSuggestedActionCache(raw string) []assistant.SuggestedAction {
	lines := strings.Split(strings.TrimSpace(raw), "\n")
	items := make([]assistant.SuggestedAction, 0, len(lines))
	for _, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		parts := strings.Split(line, "|")
		if len(parts) < 3 {
			continue
		}
		item := assistant.SuggestedAction{ActionID: parts[0], Type: parts[1], Label: parts[2]}
		if len(parts) > 3 {
			item.Icon = parts[3]
		}
		items = append(items, item)
	}
	return items
}

func filterTasks(items []assistant.AssistantUserTaskView, limit int, status string) []assistant.AssistantUserTaskView {
	filtered := make([]assistant.AssistantUserTaskView, 0, len(items))
	status = strings.TrimSpace(status)
	for _, item := range items {
		if status != "" && item.Status != status {
			continue
		}
		filtered = append(filtered, item)
	}
	if len(filtered) > limit {
		filtered = filtered[:limit]
	}
	return filtered
}

func dedupeSuggestedActions(items []assistant.SuggestedAction) []assistant.SuggestedAction {
	seen := map[string]struct{}{}
	out := make([]assistant.SuggestedAction, 0, len(items))
	for _, item := range items {
		key := strings.TrimSpace(item.ActionID)
		if key == "" {
			key = strings.TrimSpace(item.Type) + "|" + strings.TrimSpace(item.Label)
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, item)
	}
	return out
}

func dedupeTasks(items []assistant.AssistantUserTaskView) []assistant.AssistantUserTaskView {
	seen := map[string]struct{}{}
	out := make([]assistant.AssistantUserTaskView, 0, len(items))
	for _, item := range items {
		key := strings.TrimSpace(item.TaskID)
		if key == "" {
			key = strings.TrimSpace(item.Title)
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, item)
	}
	return out
}

func selectLowestMetric(profile *assistant.AssistantLearningProfile) (string, float64) {
	if profile == nil || len(profile.LatestMetricScores) == 0 {
		return "", 0
	}
	keys := make([]string, 0, len(profile.LatestMetricScores))
	for key := range profile.LatestMetricScores {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	selected := keys[0]
	lowest := profile.LatestMetricScores[selected]
	for _, key := range keys[1:] {
		if value := profile.LatestMetricScores[key]; value < lowest {
			selected = key
			lowest = value
		}
	}
	return selected, lowest
}

func topReasonCodes(counts map[string]int64, limit int) []string {
	if len(counts) == 0 || limit <= 0 {
		return nil
	}
	type pair struct {
		key   string
		count int64
	}
	items := make([]pair, 0, len(counts))
	for key, count := range counts {
		items = append(items, pair{key: key, count: count})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].count != items[j].count {
			return items[i].count > items[j].count
		}
		return items[i].key < items[j].key
	})
	if len(items) > limit {
		items = items[:limit]
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		out = append(out, item.key)
	}
	return out
}

func cloneMetricScores(src map[string]float64) map[string]float64 {
	if len(src) == 0 {
		return nil
	}
	out := make(map[string]float64, len(src))
	for key, value := range src {
		out[key] = value
	}
	return out
}

func fallbackUser(userID string) string {
	if strings.TrimSpace(userID) == "" {
		return "anonymous"
	}
	return userID
}

// consentID 为每次授权生成唯一事实 id（版本化流水：撤权后再授权产生新行，
// 历史行永久保留供审计）；同一时刻最多一条 active 由 partial unique index 保证。
func consentID(userID, skillID string, grantedAt time.Time) string {
	return strings.TrimSpace(userID) + ":" + strings.TrimSpace(skillID) + ":" +
		strconv.FormatInt(grantedAt.UTC().UnixNano(), 36)
}

func SortConsents(items []assistant.SkillConsent) {
	sort.Slice(items, func(i, j int) bool {
		return items[i].GrantedAt.After(items[j].GrantedAt)
	})
}

func IsNotFound(err error) bool {
	return errors.Is(err, rtredis.ErrKeyNotFound)
}
