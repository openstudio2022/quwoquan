package application

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

var supportedBehaviorActions = map[string]struct{}{
	"impression": {},
	"click":      {},
	"dwell":      {},
	"like":       {},
	"favorite":   {},
	"share":      {},
	"dislike":    {},
	"report":     {},
}

type BehaviorEventInput struct {
	UserID    string   `json:"userId"`
	SessionID string   `json:"sessionId"`
	ContentID string   `json:"contentId"`
	Action    string   `json:"action"`
	Tags      []string `json:"tags"`
	Duration  float64  `json:"duration"`
}

type BehaviorService struct {
	hotPath rtrec.SignalProcessor
	store   *persistence.PostStore
}

func NewBehaviorService(hotPath rtrec.SignalProcessor, store *persistence.PostStore) *BehaviorService {
	return &BehaviorService{
		hotPath: hotPath,
		store:   store,
	}
}

func (s *BehaviorService) ProcessBatch(ctx context.Context, events []BehaviorEventInput) error {
	if len(events) == 0 {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "events 不能为空", "empty behavior events")
	}
	signals := make([]rtrec.BehaviorSignal, 0, len(events))
	for _, event := range events {
		action := strings.TrimSpace(strings.ToLower(event.Action))
		if _, ok := supportedBehaviorActions[action]; !ok {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "action 不支持", "unsupported action: "+event.Action)
		}
		userID := strings.TrimSpace(event.UserID)
		if userID == "" {
			userID = "guest"
		}
		contentID := strings.TrimSpace(event.ContentID)
		if contentID == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "contentId 必填", "missing contentId")
		}
		tags := event.Tags
		if len(tags) == 0 {
			if post, ok := s.store.FindByID(ctx, contentID); ok {
				tags = behaviorTagsFromAny(post.Tags)
			}
		}
		signals = append(signals, rtrec.BehaviorSignal{
			UserID:    userID,
			SessionID: strings.TrimSpace(event.SessionID),
			ContentID: contentID,
			Action:    action,
			Tags:      tags,
			Duration:  event.Duration,
			Timestamp: time.Now().UTC(),
		})
	}
	return s.hotPath.ProcessSignalBatch(ctx, signals)
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
