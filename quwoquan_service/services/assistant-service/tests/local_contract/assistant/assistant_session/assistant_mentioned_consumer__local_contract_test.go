// spec_ref: specs/feature-tree/runtime/runtime-assistant/assistant-mentioned-consumer/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/stream"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
)

type assistantSessionAssistantMentionedConsumerMentionHandlerSpy struct {
	events []orchestration.AssistantMentionedEvent
	err    error
}

func (s *assistantSessionAssistantMentionedConsumerMentionHandlerSpy) HandleAssistantMentioned(_ context.Context, evt orchestration.AssistantMentionedEvent) error {
	s.events = append(s.events, evt)
	return s.err
}

func TestAssistantMentionedConsumerProcessesAndAcks(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	handler := &assistantSessionAssistantMentionedConsumerMentionHandlerSpy{}
	consumer := NewAssistantMentionedConsumerWithTransport(
		assistantSessionAssistantMentionedConsumerNewTestMessageTransport(t, redis),
		handler,
		"worker-1",
		nil,
	)

	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, AssistantMentionedStream, map[string]string{
		"conversationId":    "conv-1",
		"messageId":         "msg-1",
		"seq":               "12",
		"senderAccountId":   "account-a",
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
	if len(handler.events) != 1 {
		t.Fatalf("events=%d, want 1", len(handler.events))
	}
	got := handler.events[0]
	if got.ChatConversationID != "conv-1" || got.Seq != 12 ||
		got.SenderAccountID != "account-a" || got.SenderID != "user-a" ||
		got.AssistantMemberID != "assistant" {
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
	handler := &assistantSessionAssistantMentionedConsumerMentionHandlerSpy{err: errors.New("boom")}
	consumer := NewAssistantMentionedConsumerWithTransport(
		assistantSessionAssistantMentionedConsumerNewTestMessageTransport(t, redis),
		handler,
		"worker-1",
		nil,
	)

	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, AssistantMentionedStream, map[string]string{
		"conversationId":    "conv-1",
		"messageId":         "msg-1",
		"seq":               "12",
		"senderAccountId":   "account-a",
		"senderId":          "user-a",
		"content":           "@小趣 总结",
		"assistantMemberId": "assistant",
		"error":             "private upstream detail",
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
	if dlq[0].Values["errorDigest"] == "" {
		t.Fatalf("dlq must retain an error digest: %#v", dlq[0].Values)
	}
	if _, containsRawError := dlq[0].Values["error"]; containsRawError {
		t.Fatalf("dlq must not retain raw error: %#v", dlq[0].Values)
	}
	pending, err := redis.XReadGroup(ctx, AssistantMentionedConsumerGroup, "worker-1", map[string]string{AssistantMentionedStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("read pending: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d, want 0 after durable DLQ ACK", len(pending))
	}
	if dlq[0].Values["sourceId"] == "" ||
		dlq[0].Values["reason"] != "handler_failed" ||
		dlq[0].Values["conversationId"] != "conv-1" ||
		dlq[0].Values["messageId"] != "msg-1" {
		t.Fatalf("dlq lost replay coordinates or event fields: %#v", dlq[0].Values)
	}

	handler.err = nil
	replayFields := make(map[string]string, len(dlq[0].Values))
	for key, value := range dlq[0].Values {
		switch key {
		case "sourceId", "reason", "errorDigest":
			continue
		default:
			replayFields[key] = value
		}
	}
	if _, err := redis.XAdd(ctx, AssistantMentionedStream, replayFields); err != nil {
		t.Fatalf("requeue dead letter: %v", err)
	}
	replayed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("process replayed dead letter: %v", err)
	}
	if replayed != 1 || len(handler.events) != 2 {
		t.Fatalf(
			"replayed=%d handler events=%d, want 1 and 2",
			replayed,
			len(handler.events),
		)
	}
}

func TestAssistantMentionedConsumerDeduplicatesByChatConversationMessage(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	handler := &assistantSessionAssistantMentionedConsumerMentionHandlerSpy{}
	consumer := NewAssistantMentionedConsumerWithTransport(
		assistantSessionAssistantMentionedConsumerNewTestMessageTransport(t, redis),
		handler,
		"worker-1",
		nil,
	)

	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	for i := 0; i < 2; i++ {
		if _, err := redis.XAdd(ctx, AssistantMentionedStream, map[string]string{
			"conversationId":    "conv-1",
			"messageId":         "msg-1",
			"seq":               "12",
			"senderAccountId":   "account-a",
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

func assistantSessionAssistantMentionedConsumerNewTestMessageTransport(
	t *testing.T,
	client rtredis.Client,
) *runtimemessaging.RedisMessageTransport {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"assistant-service-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("NewRedisMessageTransportForRoot() error = %v", err)
	}
	return transport
}
