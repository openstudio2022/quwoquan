package local_contract

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	streamadapter "quwoquan_service/services/notification-service/internal/adapters/stream"
	"quwoquan_service/services/notification-service/internal/application"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

type memoryAppMessageStore struct {
	mu       sync.Mutex
	byKey    map[string]notification.AppMessage
	inserted int
}

func newMemoryAppMessageStore() *memoryAppMessageStore {
	return &memoryAppMessageStore{byKey: map[string]notification.AppMessage{}}
}

func (s *memoryAppMessageStore) Create(
	_ context.Context,
	message notification.AppMessage,
) (notification.AppMessage, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if existing, ok := s.byKey[message.IdempotencyKey]; ok {
		return existing, false, nil
	}
	s.byKey[message.IdempotencyKey] = message
	s.inserted++
	return message, true, nil
}

func (s *memoryAppMessageStore) FindByIdempotencyKey(
	_ context.Context,
	key string,
) (notification.AppMessage, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	message, ok := s.byKey[key]
	return message, ok, nil
}

func (s *memoryAppMessageStore) Acknowledge(
	_ context.Context, _, _ string, _ time.Time,
) (notification.AppMessage, error) {
	return notification.AppMessage{}, fmt.Errorf("not used")
}

func (s *memoryAppMessageStore) MarkRead(
	_ context.Context, _, _ string, _ time.Time,
) (notification.AppMessage, error) {
	return notification.AppMessage{}, fmt.Errorf("not used")
}

func (s *memoryAppMessageStore) insertedCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.inserted
}

type passthroughTx struct{}

func (passthroughTx) RunInTransaction(ctx context.Context, fn func(context.Context) error) error {
	return fn(ctx)
}

type noopDeliveryOutbox struct{}

func (noopDeliveryOutbox) CreateNotification(
	_ context.Context,
	record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	return record, nil
}

type memoryFailureStore struct {
	mu       sync.Mutex
	attempts map[string]int64
}

func newMemoryFailureStore() *memoryFailureStore {
	return &memoryFailureStore{attempts: map[string]int64{}}
}

func (s *memoryFailureStore) RecordInteractionFailure(
	_ context.Context, stream, messageID, _ string, _ error,
) (int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := stream + "|" + messageID
	s.attempts[key]++
	return s.attempts[key], nil
}

func (s *memoryFailureStore) ClearInteractionFailure(
	_ context.Context, stream, messageID string,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.attempts, stream+"|"+messageID)
	return nil
}

func newConsumerFixture(t *testing.T) (
	*streamadapter.InteractionNotificationConsumer,
	rtredis.Client,
	*memoryAppMessageStore,
) {
	t.Helper()
	redis := rtredis.NewMemoryClient()
	store := newMemoryAppMessageStore()
	facade, err := application.NewAppMessageCommandFacade(
		store, passthroughTx{}, noopDeliveryOutbox{},
	)
	if err != nil {
		t.Fatalf("facade init: %v", err)
	}
	consumer, err := streamadapter.NewInteractionNotificationConsumer(
		redis, facade, newMemoryFailureStore(), "test-consumer", nil,
	)
	if err != nil {
		t.Fatalf("consumer init: %v", err)
	}
	return consumer, redis, store
}

func appendCommentCreated(t *testing.T, redis rtredis.Client, eventID string) {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"commentId": "cmt-1", "postId": "post-1", "version": 1,
		"postAuthorId": "author-1", "authorId": "actor-1",
		"createdAt": time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	if _, err := redis.XAdd(context.Background(), "events.content.comment_lifecycle", map[string]string{
		"eventId":          eventID,
		"eventType":        "CommentCreated",
		"aggregateType":    "Comment",
		"aggregateId":      "cmt-1",
		"aggregateVersion": "1",
		"payload":          string(payload),
		"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd: %v", err)
	}
}

func TestInteractionConsumerProjectsOnceAndDedupesReplay(t *testing.T) {
	consumer, redis, store := newConsumerFixture(t)
	ctx := context.Background()

	appendCommentCreated(t, redis, "evt-comment-1")
	// 同一事件重复投递（at-least-once transport 的重放）。
	appendCommentCreated(t, redis, "evt-comment-1")

	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("process: %v", err)
	}
	if store.insertedCount() != 1 {
		t.Fatalf("inserted=%d want=1 (idempotency key must dedupe replay)", store.insertedCount())
	}
	message, found, err := store.FindByIdempotencyKey(
		ctx,
		application.InteractionNotificationIdempotencyKey(
			"CommentCreated",
			"evt-comment-1",
			"author-1",
			"comment",
			"cmt-1",
		),
	)
	if err != nil || !found {
		t.Fatalf("app message missing: found=%v err=%v", found, err)
	}
	if message.UserID != "author-1" || message.MessageType != "content" {
		t.Fatalf("unexpected app message: %+v", message)
	}
}

func TestInteractionConsumerDeadLettersPoisonEventAndContinues(t *testing.T) {
	consumer, redis, store := newConsumerFixture(t)
	ctx := context.Background()

	// 缺接收者且缺 comment 身份 → 投影结构化失败 → 重试计满进 DLQ。
	if _, err := redis.XAdd(ctx, "events.content.comment_lifecycle", map[string]string{
		"eventId":    "evt-poison-1",
		"eventType":  "CommentCreated",
		"payload":    `{"unexpected":true}`,
		"occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd poison: %v", err)
	}
	appendCommentCreated(t, redis, "evt-comment-2")

	var lastErr error
	for attempt := 0; attempt < 6; attempt++ {
		_, lastErr = consumer.ProcessOnce(ctx)
	}
	if lastErr != nil {
		t.Fatalf("after dead-letter the scan must be clean: %v", lastErr)
	}
	if store.insertedCount() != 1 {
		t.Fatalf("healthy event must still project: inserted=%d", store.insertedCount())
	}
	dlq, err := redis.XReadGroup(
		ctx, "dlq-observer", "observer",
		map[string]string{"events.content.comment_lifecycle.notification-dlq": ">"},
		10, 10*time.Millisecond,
	)
	if err != nil {
		if groupErr := redis.XGroupCreateMkStream(
			ctx, "events.content.comment_lifecycle.notification-dlq", "dlq-observer", "0",
		); groupErr != nil {
			t.Fatalf("observe dlq group: %v", groupErr)
		}
		dlq, err = redis.XReadGroup(
			ctx, "dlq-observer", "observer",
			map[string]string{"events.content.comment_lifecycle.notification-dlq": ">"},
			10, 10*time.Millisecond,
		)
		if err != nil {
			t.Fatalf("observe dlq: %v", err)
		}
	}
	if len(dlq) != 1 {
		t.Fatalf("dlq entries=%d want=1", len(dlq))
	}
	if !strings.Contains(dlq[0].Values["error"], "CommentCreated") {
		t.Fatalf("dlq entry must carry the structured cause: %v", dlq[0].Values)
	}
}
