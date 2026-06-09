package messaging

import (
	"context"
	"errors"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/application"
)

type mentionHandlerSpy struct {
	events []application.AssistantMentionedEvent
	err    error
}

func (s *mentionHandlerSpy) HandleAssistantMentioned(_ context.Context, evt application.AssistantMentionedEvent) error {
	s.events = append(s.events, evt)
	return s.err
}

func TestAssistantMentionedConsumerProcessesAndAcks(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	handler := &mentionHandlerSpy{}
	consumer := NewAssistantMentionedConsumer(redis, handler, "worker-1", nil)

	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, AssistantMentionedStream, map[string]string{
		"conversationId":    "conv-1",
		"messageId":         "msg-1",
		"seq":               "12",
		"senderId":          "user-a",
		"content":           "@小趣 总结",
		"assistantMemberId": "assistant",
		"assistantSkillId":  "general",
	}); err != nil {
		t.Fatalf("XAdd: %v", err)
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("ProcessOnce: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d, want 1", processed)
	}
	if len(handler.events) != 1 {
		t.Fatalf("events=%d, want 1", len(handler.events))
	}
	got := handler.events[0]
	if got.ConversationID != "conv-1" || got.Seq != 12 || got.AssistantMemberID != "assistant" {
		t.Fatalf("event=%#v", got)
	}
	pending, err := redis.XReadGroup(ctx, AssistantMentionedConsumerGroup, "worker-1", map[string]string{AssistantMentionedStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("read pending: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d, want 0", len(pending))
	}
}

func TestAssistantMentionedConsumerDeadLettersFailedMessage(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	handler := &mentionHandlerSpy{err: errors.New("boom")}
	consumer := NewAssistantMentionedConsumer(redis, handler, "worker-1", nil)

	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, AssistantMentionedStream, map[string]string{
		"conversationId":    "conv-1",
		"messageId":         "msg-1",
		"seq":               "12",
		"senderId":          "user-a",
		"content":           "@小趣 总结",
		"assistantMemberId": "assistant",
	}); err != nil {
		t.Fatalf("XAdd: %v", err)
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("ProcessOnce: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d, want 1", processed)
	}
	if err := redis.XGroupCreateMkStream(ctx, AssistantMentionedDeadLetter, "dlq-test", "0"); err != nil {
		t.Fatalf("create dlq group: %v", err)
	}
	dlq, err := redis.XReadGroup(ctx, "dlq-test", "worker-1", map[string]string{AssistantMentionedDeadLetter: ">"}, 10, 0)
	if err != nil {
		t.Fatalf("read dlq: %v", err)
	}
	if len(dlq) != 1 {
		t.Fatalf("dlq=%d, want 1", len(dlq))
	}
	if dlq[0].Values["error"] != "boom" {
		t.Fatalf("dlq error=%s", dlq[0].Values["error"])
	}
	pending, err := redis.XReadGroup(ctx, AssistantMentionedConsumerGroup, "worker-1", map[string]string{AssistantMentionedStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("read pending: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("pending=%d, want 1 for retry", len(pending))
	}
}

func TestAssistantMentionedConsumerDeduplicatesByConversationMessage(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	handler := &mentionHandlerSpy{}
	consumer := NewAssistantMentionedConsumer(redis, handler, "worker-1", nil)

	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	for i := 0; i < 2; i++ {
		if _, err := redis.XAdd(ctx, AssistantMentionedStream, map[string]string{
			"conversationId":    "conv-1",
			"messageId":         "msg-1",
			"seq":               "12",
			"senderId":          "user-a",
			"content":           "@小趣 总结",
			"assistantMemberId": "assistant",
		}); err != nil {
			t.Fatalf("XAdd[%d]: %v", i, err)
		}
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("ProcessOnce: %v", err)
	}
	if processed != 2 {
		t.Fatalf("processed=%d, want 2 including dedup ack", processed)
	}
	if len(handler.events) != 1 {
		t.Fatalf("handler events=%d, want 1", len(handler.events))
	}
	pending, err := redis.XReadGroup(ctx, AssistantMentionedConsumerGroup, "worker-1", map[string]string{AssistantMentionedStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("read pending: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d, want 0", len(pending))
	}
}
