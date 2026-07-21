package messaging

import (
	"context"
	"errors"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	groupapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group"
)

func TestCircleGroupConversationBindingConsumerAppliesAndAcknowledges(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	projector := &memoryConversationBindingProjection{}
	failures := &memoryConversationBindingFailures{}
	consumer, err := NewCircleGroupConversationBindingConsumer(
		newCircleTestMessageTransport(t, client),
		projector,
		failures,
		"circle-binding-test",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := client.XAdd(ctx, CircleGroupConversationProvisionedStream, validCircleGroupConversationProvisionedValues("binding-1")); err != nil {
		t.Fatal(err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 {
		t.Fatalf("processed=%d err=%v", processed, err)
	}
	if len(projector.facts) != 1 || projector.facts[0].ConversationID != "conversation-1" {
		t.Fatalf("binding fact lost: %#v", projector.facts)
	}
	pending, _, err := client.XAutoClaim(
		ctx,
		CircleGroupConversationProvisionedStream,
		CircleGroupConversationBindingGroup,
		"observer",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(pending) != 0 {
		t.Fatalf("successful binding must ACK source message, pending=%d", len(pending))
	}
}

func TestCircleGroupConversationBindingConsumerKeepsFailurePending(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	projector := &memoryConversationBindingProjection{err: errors.New("projection failure")}
	failures := &memoryConversationBindingFailures{}
	consumer, err := NewCircleGroupConversationBindingConsumer(
		newCircleTestMessageTransport(t, client),
		projector,
		failures,
		"circle-binding-failure-test",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := client.XAdd(ctx, CircleGroupConversationProvisionedStream, validCircleGroupConversationProvisionedValues("binding-failure")); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err == nil || processed != 0 {
		t.Fatalf("first projection failure must remain pending, processed=%d err=%v", processed, err)
	}
	if failures.attempts == 0 {
		t.Fatal("failure count must persist before retry")
	}
}

type memoryConversationBindingProjection struct {
	facts []groupapp.ConversationProvisionedFact
	err   error
}

func (p *memoryConversationBindingProjection) Apply(
	_ context.Context,
	fact groupapp.ConversationProvisionedFact,
) error {
	p.facts = append(p.facts, fact)
	return p.err
}

type memoryConversationBindingFailures struct {
	attempts int64
}

func (s *memoryConversationBindingFailures) RecordCircleGroupConversationBindingFailure(
	_ context.Context,
	_ string,
	_ string,
	_ string,
) (int64, error) {
	s.attempts++
	return s.attempts, nil
}

func (s *memoryConversationBindingFailures) ClearCircleGroupConversationBindingFailure(
	context.Context,
	string,
) error {
	return nil
}

func validCircleGroupConversationProvisionedValues(eventID string) map[string]string {
	return map[string]string{
		"eventId":   eventID,
		"eventType": circleGroupConversationProvisionedEventType,
		"payload": `{
			"conversationId":"conversation-1",
			"circleId":"circle-1",
			"circleGroupId":"group-1"
		}`,
		"occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
}
