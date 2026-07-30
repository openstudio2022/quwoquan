package behavior_test

// N0-4 契约：SessionCache 主动失效必须用 feed 读路径的 sessionId（feedSessionId，
// FeedSession 滚动 UUID），而不是行为批次的跨服务 trace sessionId。此前 key 错配
// 导致行为后 L1 缓存失效永不命中（实时反馈延迟退化为纯 TTL 2s + 特征滞后）。

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	"testing"

	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func TestProcessBatchInvalidatesSessionCacheWithFeedSessionID(t *testing.T) {
	processor := &fakeSignalProcessor{}
	store := persistence.NewPostStore([]postmodel.Post{})

	var invalidatedUser, invalidatedSession string
	svc := NewBehaviorService(processor, store,
		WithSessionCacheInvalidator(func(userID, sessionID string) {
			invalidatedUser, invalidatedSession = userID, sessionID
		}),
	)

	err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{
		{
			ClientEventID: "evt-invalidate-001",
			OccurredAt:    validBehaviorOccurredAt(),
			UserID:        "user_inv_1",
			SessionID:     "trace-session-base36", // 跨服务 trace，非缓存 key
			FeedSessionID: "feed-session-uuid-1",  // SessionCache 的真实 key
			ContentID:     "post_inv_1",
			Action:        "click",
		},
	})
	if err != nil {
		t.Fatalf("process batch: %v", err)
	}
	if invalidatedUser != "user_inv_1" {
		t.Fatalf("invalidate user want user_inv_1, got %q", invalidatedUser)
	}
	if invalidatedSession != "feed-session-uuid-1" {
		t.Fatalf("invalidate session must use feedSessionId, got %q", invalidatedSession)
	}
}

func TestProcessBatchDoesNotGuessCacheKeyFromTraceSessionID(t *testing.T) {
	processor := &fakeSignalProcessor{}
	store := persistence.NewPostStore([]postmodel.Post{})

	var invalidatedSession string
	svc := NewBehaviorService(processor, store,
		WithSessionCacheInvalidator(func(_, sessionID string) {
			invalidatedSession = sessionID
		}),
	)

	err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{
		{
			ClientEventID: "evt-invalidate-002",
			OccurredAt:    validBehaviorOccurredAt(),
			UserID:        "user_inv_2",
			SessionID:     "trace-only-session",
			ContentID:     "post_inv_2",
			Action:        "click",
		},
	})
	if err != nil {
		t.Fatalf("process batch: %v", err)
	}
	if invalidatedSession != "" {
		t.Fatalf("trace sessionId must not be used as feed cache key, got %q", invalidatedSession)
	}
}
