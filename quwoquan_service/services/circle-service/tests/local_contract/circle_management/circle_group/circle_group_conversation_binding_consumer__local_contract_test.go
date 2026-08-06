// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002
// readiness_case: bind-circle-group-conversation-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/messaging"
)

func TestCircleGroupConversationBindingConsumerAppliesAndAcknowledges(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	projector := &memoryConversationBindingProjection{}
	failures := &memoryConversationBindingFailures{}
	consumer, err := NewCircleGroupConversationBindingConsumer(
		newCircleGroupTestMessageTransport(t, client),
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
		newCircleGroupTestMessageTransport(t, client),
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
		"eventType": "CircleGroupConversationProvisioned",
		"payload": `{
			"conversationId":"conversation-1",
			"circleId":"circle-1",
			"circleGroupId":"group-1"
		}`,
		"occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
}

func newCircleGroupTestMessageTransport(
	t *testing.T,
	client rtredis.Client,
) *runtimemessaging.RedisMessageTransport {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"circle-group-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("new CircleGroup test message transport: %v", err)
	}
	return transport
}
