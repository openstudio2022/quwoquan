package assistant_policy_release_test

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	releasemessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/messaging"
)

type policyOutboxStoreStub struct {
	events []runtimemessaging.LeasedDurableOutboxEvent
	marked []string
}

func (store *policyOutboxStoreStub) ClaimPendingOutbox(
	context.Context,
	string,
	time.Duration,
	int,
) ([]runtimemessaging.LeasedDurableOutboxEvent, error) {
	return store.events, nil
}

func (store *policyOutboxStoreStub) MarkOutboxPublished(
	_ context.Context,
	eventID string,
	_ string,
	reference string,
	_ time.Time,
) error {
	store.marked = append(store.marked, eventID+":"+reference)
	return nil
}

func (*policyOutboxStoreStub) ReleaseOutboxClaim(
	context.Context,
	string,
	string,
) error {
	return nil
}

type policyOutboxPublisherStub struct {
	messages []runtimemessaging.DurableMessage
}

func (publisher *policyOutboxPublisherStub) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	publisher.messages = append(publisher.messages, message)
	return "stream-1", nil
}

func (*policyOutboxPublisherStub) SetDurableRetention(
	context.Context,
	string,
	time.Duration,
) error {
	return nil
}

func TestOutboxRelayPublishesReleaseAggregateVersion(t *testing.T) {
	t.Parallel()
	store := &policyOutboxStoreStub{
		events: []runtimemessaging.LeasedDurableOutboxEvent{{
			ID:               "policy-release:1",
			EventType:        "AssistantPolicyReleaseStaged",
			AggregateType:    "AssistantPolicyRelease",
			AggregateID:      "assistant-default",
			AggregateVersion: 1,
			Payload:          `{"policyId":"assistant-default"}`,
			OccurredAt:       time.Date(2026, 7, 26, 1, 2, 3, 0, time.UTC),
		}},
	}
	publisher := &policyOutboxPublisherStub{}
	relay, err := releasemessaging.NewOutboxRelay(
		"release",
		store,
		publisher,
		time.Second,
		1,
		nil,
	)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}

	published, err := relay.FlushOnce(context.Background())
	if err != nil {
		t.Fatalf("FlushOnce() error = %v", err)
	}
	if published != 1 || len(publisher.messages) != 1 {
		t.Fatalf("published/messages = %d/%d, want 1/1", published, len(publisher.messages))
	}
	fields := make(map[string]string, len(publisher.messages[0].Fields))
	for _, field := range publisher.messages[0].Fields {
		fields[field.Name] = field.Value
	}
	if fields["aggregateVersion"] != "1" {
		t.Fatalf("aggregateVersion = %q, want 1", fields["aggregateVersion"])
	}
	if len(store.marked) != 1 || store.marked[0] != "policy-release:1:stream-1" {
		t.Fatalf("marked = %v", store.marked)
	}
}
