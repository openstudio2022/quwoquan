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

var supportedBehaviorActions = map[string]struct{}{
	"impression": {},
	"click":      {},
	"dwell":      {},
	"favorite":   {},
	"share":      {},
	"dislike":    {},
	"report":     {},
}

type BehaviorEventInput struct {
	UserID       string   `json:"userId"`
	SessionID    string   `json:"sessionId"`
	ContentID    string   `json:"contentId"`
	PostID       string   `json:"postId"`
	Action       string   `json:"action"`
	Type         string   `json:"type"`
	Tags         []string `json:"tags"`
	Duration     float64  `json:"duration"`
	DwellMs      float64  `json:"dwellMs"`
	FeedPosition int      `json:"feedPosition"`
}

type BehaviorService struct {
	hotPath   rtrec.SignalProcessor
	store     persistence.PostRepository
	publisher repository.EventPublisher
	projector Projector
	feedback  *rtrec.FeedbackRecorder
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
		userID := strings.TrimSpace(eventInput.UserID)
		if userID == "" {
			userID = "guest"
		}
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
		signal := rtrec.BehaviorSignal{
			UserID:    userID,
			SessionID: strings.TrimSpace(eventInput.SessionID),
			ContentID: contentID,
			Action:    action,
			Tags:      tags,
			Duration:  duration,
			Timestamp: occurredAt,
		}
		signals = append(signals, signal)
		projectedEvents = append(projectedEvents, map[string]any{
			"userId":    userID,
			"sessionId": signal.SessionID,
			"contentId": contentID,
			"action":    action,
			"tags":      append([]string(nil), tags...),
			"duration":  duration,
			"timestamp": occurredAt.Format(time.RFC3339),
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
