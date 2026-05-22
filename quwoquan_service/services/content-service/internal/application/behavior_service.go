package application

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/repository"
	"quwoquan_service/services/content-service/internal/domain/post/event"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// supportedBehaviorActions derives from SignalWeights (single source of truth
// aligned with behaviors.yaml signal_weight). An action is supported iff it
// has a weight entry, preventing silent drift between the two maps.
var supportedBehaviorActions = func() map[string]struct{} {
	m := make(map[string]struct{}, len(rtrec.SignalWeights))
	for action := range rtrec.SignalWeights {
		m[action] = struct{}{}
	}
	return m
}()

type BehaviorEventInput struct {
	UserID          string   `json:"userId"`
	SessionID       string   `json:"sessionId"`
	FeedSessionID   string   `json:"feedSessionId"`
	ContentID       string   `json:"contentId"`
	PostID          string   `json:"postId"`
	Action          string   `json:"action"`
	Type            string   `json:"type"`
	ContentType     string   `json:"contentType"`
	Tags            []string `json:"tags"`
	Duration        float64  `json:"duration"`
	DwellMs         float64  `json:"dwellMs"`
	FeedPosition    int      `json:"feedPosition"`
	Position        int      `json:"position"`
	AuthorID        string   `json:"authorId"`
	ReferralSource  string   `json:"referralSource"`
	EngagementDepth int      `json:"engagementDepth"`
	ConsumedRatio   float64  `json:"consumedRatio"`
	TotalUnits      int      `json:"totalUnits"`
	EntityRefs      []string `json:"entityRefs"`
	FeedRequestID   string   `json:"feedRequestId"`
	CommentLength   int      `json:"commentLength"`
}

type BehaviorService struct {
	hotPath        rtrec.SignalProcessor
	store          persistence.PostRepository
	publisher      repository.EventPublisher
	projector      Projector
	feedback       *rtrec.FeedbackRecorder
	eventStore     persistence.BehaviorEventStore
	metricsStore   *persistence.DailyMetricsStore
	sessionInvalid func(userID, sessionID string)
}

type BehaviorServiceOption func(*BehaviorService)

func WithBehaviorEventPublisher(pub repository.EventPublisher) BehaviorServiceOption {
	return func(s *BehaviorService) { s.publisher = pub }
}

func WithBehaviorProjector(p Projector) BehaviorServiceOption {
	return func(s *BehaviorService) { s.projector = p }
}

func WithBehaviorFeedbackRecorder(f *rtrec.FeedbackRecorder) BehaviorServiceOption {
	return func(s *BehaviorService) { s.feedback = f }
}

func WithSessionCacheInvalidator(fn func(userID, sessionID string)) BehaviorServiceOption {
	return func(s *BehaviorService) { s.sessionInvalid = fn }
}

func WithBehaviorEventStore(es persistence.BehaviorEventStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.eventStore = es }
}

func WithDailyMetricsStore(ms *persistence.DailyMetricsStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.metricsStore = ms }
}

func NewBehaviorService(hotPath rtrec.SignalProcessor, store persistence.PostRepository, opts ...BehaviorServiceOption) *BehaviorService {
	svc := &BehaviorService{
		hotPath: hotPath,
		store:   store,
	}
	for _, opt := range opts {
		if opt != nil {
			opt(svc)
		}
	}
	return svc
}

func (s *BehaviorService) ProcessBatch(ctx context.Context, events []BehaviorEventInput) error {
	if len(events) == 0 {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "events 不能为空", "empty behavior events")
	}
	signals := make([]rtrec.BehaviorSignal, 0, len(events))
	projectedEvents := make([]map[string]any, 0, len(events))
	occurredAt := time.Now().UTC()
	batchUserID := ""
	batchSessionID := ""
	for _, eventInput := range events {
		action := normalizeBehaviorAction(eventInput)
		if _, ok := supportedBehaviorActions[action]; !ok {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "action 不支持", "unsupported action: "+firstNonEmptyLocal(eventInput.Action, eventInput.Type))
		}
		userID := normalizeAnonymousSubAccountID(eventInput.UserID)
		contentID := strings.TrimSpace(firstNonEmptyLocal(eventInput.ContentID, eventInput.PostID))
		if contentID == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "contentId 必填", "missing contentId")
		}
		duration := eventInput.Duration
		if duration == 0 && eventInput.DwellMs > 0 {
			duration = eventInput.DwellMs / 1000
		}
		tags := eventInput.Tags
		if len(tags) == 0 {
			if post, ok := s.store.FindByID(ctx, contentID); ok {
				tags = behaviorTagsFromAny(post.Tags)
			}
		}
		feedPos := eventInput.FeedPosition
		if feedPos == 0 && eventInput.Position > 0 {
			feedPos = eventInput.Position
		}
		signal := rtrec.BehaviorSignal{
			UserID:          userID,
			SessionID:       strings.TrimSpace(eventInput.SessionID),
			FeedSessionID:   strings.TrimSpace(eventInput.FeedSessionID),
			ContentID:       contentID,
			Action:          action,
			ContentType:     strings.TrimSpace(eventInput.ContentType),
			Tags:            tags,
			Duration:        duration,
			Timestamp:       occurredAt,
			AuthorID:        strings.TrimSpace(eventInput.AuthorID),
			ReferralSource:  strings.TrimSpace(eventInput.ReferralSource),
			EngagementDepth: eventInput.EngagementDepth,
			ConsumedRatio:   eventInput.ConsumedRatio,
			TotalUnits:      eventInput.TotalUnits,
			EntityRefs:      eventInput.EntityRefs,
			FeedRequestID:   strings.TrimSpace(eventInput.FeedRequestID),
			Position:        feedPos,
			CommentLength:   eventInput.CommentLength,
		}
		signals = append(signals, signal)
		projectedEvents = append(projectedEvents, map[string]any{
			"userId":          userID,
			"sessionId":       signal.SessionID,
			"contentId":       contentID,
			"action":          action,
			"contentType":     signal.ContentType,
			"tags":            append([]string(nil), tags...),
			"duration":        duration,
			"timestamp":       occurredAt.Format(time.RFC3339),
			"authorId":        signal.AuthorID,
			"referralSource":  signal.ReferralSource,
			"engagementDepth": signal.EngagementDepth,
			"consumedRatio":   signal.ConsumedRatio,
			"totalUnits":      signal.TotalUnits,
			"entityRefs":      signal.EntityRefs,
			"feedRequestId":   strings.TrimSpace(eventInput.FeedRequestID),
			"feedPosition":    feedPos,
			"commentLength":   eventInput.CommentLength,
		})
		if batchUserID == "" {
			batchUserID = userID
		}
		if batchSessionID == "" {
			batchSessionID = signal.SessionID
		}
	}
	if err := s.hotPath.ProcessSignalBatch(ctx, signals); err != nil {
		return err
	}
	for _, signal := range signals {
		rtrec.RecordBehaviorMetric(signal)
	}
	if s.eventStore != nil {
		rawEvents := make([]persistence.RawBehaviorEvent, len(signals))
		for i, sig := range signals {
			rawEvents[i] = persistence.RawBehaviorEvent{
				UserID:          sig.UserID,
				SessionID:       sig.SessionID,
				ContentID:       sig.ContentID,
				Action:          sig.Action,
				Tags:            sig.Tags,
				Duration:        sig.Duration,
				AuthorID:        sig.AuthorID,
				ReferralSource:  sig.ReferralSource,
				EngagementDepth: sig.EngagementDepth,
				ConsumedRatio:   sig.ConsumedRatio,
				TotalUnits:      sig.TotalUnits,
				EntityRefs:      sig.EntityRefs,
				FeedRequestID:   strings.TrimSpace(events[i].FeedRequestID),
				OccurredAt:      occurredAt.Format(time.RFC3339),
				CreatedAt:       occurredAt,
			}
		}
		_ = s.eventStore.InsertBatch(ctx, rawEvents)
	}
	if s.metricsStore != nil {
		dateStr := occurredAt.Format("2006-01-02")
		for _, sig := range signals {
			dwellMs := int64(sig.Duration * 1000)
			_ = s.metricsStore.IncrementMetric(ctx, dateStr, "action", sig.Action, sig.Action, dwellMs, sig.EngagementDepth)
			if sig.ContentID != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, "content", sig.ContentID, sig.Action, dwellMs, sig.EngagementDepth)
			}
			if sig.AuthorID != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, "author", sig.AuthorID, sig.Action, dwellMs, sig.EngagementDepth)
			}
		}
	}
	if s.feedback != nil {
		for _, signal := range signals {
			_ = s.feedback.RecordEngagement(ctx, signal, 0)
		}
	}
	payload := map[string]any{
		"userId":     batchUserID,
		"sessionId":  batchSessionID,
		"events":     projectedEvents,
		"count":      len(projectedEvents),
		"reportedAt": occurredAt.Format(time.RFC3339),
		"source":     "content_behavior_tracker",
	}
	if s.publisher != nil {
		aggregateID := firstNonEmptyLocal(batchSessionID, batchUserID, occurredAt.Format(time.RFC3339Nano))
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          event.BehaviorBatchReported,
			AggregateType: "BehaviorBatch",
			AggregateID:   aggregateID,
			Payload:       payload,
			OccurredAt:    occurredAt.Format(time.RFC3339),
		})
	}
	if s.projector != nil {
		aggregateID := firstNonEmptyLocal(batchSessionID, batchUserID, occurredAt.Format(time.RFC3339Nano))
		if err := s.projector.Project(ctx, ProjectorEvent{
			Type:          event.BehaviorBatchReported,
			AggregateType: "BehaviorBatch",
			AggregateID:   aggregateID,
			Payload:       payload,
			OccurredAt:    occurredAt,
		}); err != nil {
			return err
		}
	}
	if s.sessionInvalid != nil && batchUserID != "" && batchSessionID != "" {
		s.sessionInvalid(batchUserID, batchSessionID)
	}
	return nil
}

func normalizeBehaviorAction(input BehaviorEventInput) string {
	return strings.TrimSpace(strings.ToLower(firstNonEmptyLocal(input.Action, input.Type)))
}

func behaviorTagsFromAny(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			if s, ok := item.(string); ok && strings.TrimSpace(s) != "" {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

func firstNonEmptyLocal(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
