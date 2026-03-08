package runtimecontext

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/recommendation"
)

const (
	pageCtxKeyFmt = "page_ctx:%s"
	pageCtxTTL    = 10 * time.Minute
)

// PageContextManager handles page context reporting and retrieval.
type PageContextManager struct {
	redis   rtredis.Client
	hotPath recommendation.SignalProcessor
}

func NewPageContextManager(redis rtredis.Client, hotPath recommendation.SignalProcessor) *PageContextManager {
	return &PageContextManager{redis: redis, hotPath: hotPath}
}

// Report stores the page context and forwards user actions to the recommendation hot path.
func (m *PageContextManager) Report(ctx context.Context, req PageContextRequest) error {
	snapshot := PageContextSnapshot{
		UserID:     req.UserID,
		SessionID:  req.SessionID,
		PageType:   req.PageType,
		Objects:    req.Objects,
		UserAction: req.UserAction,
		CapturedAt: time.Now().UTC(),
	}

	data, err := json.Marshal(snapshot)
	if err != nil {
		return fmt.Errorf("marshal page context: %w", err)
	}

	key := fmt.Sprintf(pageCtxKeyFmt, req.UserID)
	if err := m.redis.Set(ctx, key, string(data), pageCtxTTL); err != nil {
		return fmt.Errorf("store page context: %w", err)
	}

	// Forward explicit user actions to recommendation hot path
	if m.hotPath != nil && len(req.UserActions) > 0 {
		for _, ua := range req.UserActions {
			tags := extractTagsFromAction(req, ua)
			signal := recommendation.BehaviorSignal{
				UserID:    req.UserID,
				ContentID: ua.ObjectID,
				Action:    ua.Action,
				Tags:      tags,
				Timestamp: ua.Timestamp,
			}
			_ = m.hotPath.ProcessSignal(ctx, signal)
		}
	}

	return nil
}

// Get retrieves the current page context for a user.
func (m *PageContextManager) Get(ctx context.Context, userID string) (*PageContextSnapshot, error) {
	key := fmt.Sprintf(pageCtxKeyFmt, userID)
	data, err := m.redis.Get(ctx, key)
	if err != nil || data == "" {
		return nil, nil
	}

	var snapshot PageContextSnapshot
	if err := json.Unmarshal([]byte(data), &snapshot); err != nil {
		return nil, fmt.Errorf("unmarshal page context: %w", err)
	}
	return &snapshot, nil
}

// Clear removes the page context (e.g., on logout).
func (m *PageContextManager) Clear(ctx context.Context, userID string) error {
	key := fmt.Sprintf(pageCtxKeyFmt, userID)
	return m.redis.Del(ctx, key)
}

func extractTagsFromAction(req PageContextRequest, ua UserActionEvent) []string {
	if req.Objects.Post != nil {
		return req.Objects.Post.Tags
	}
	for _, p := range req.Objects.Posts {
		if p.ID == ua.ObjectID {
			return p.Tags
		}
	}
	return nil
}
