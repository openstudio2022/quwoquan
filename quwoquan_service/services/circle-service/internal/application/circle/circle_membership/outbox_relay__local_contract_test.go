package circlemembership

import (
	"context"
	"errors"
	"testing"
	"time"

	membershipports "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/ports"
)

type membershipRelayStore struct {
	events     []membershipports.OutboxEvent
	checkpoint string
}

func (store *membershipRelayStore) ReadAfter(_ context.Context, checkpoint string, _ int) ([]membershipports.OutboxEvent, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return store.events, nil
}

func (store *membershipRelayStore) LoadCheckpoint(context.Context, string) (string, error) {
	return store.checkpoint, nil
}

func (store *membershipRelayStore) SaveCheckpoint(_ context.Context, _ string, checkpoint string) error {
	store.checkpoint = checkpoint
	return nil
}

type membershipRelayPublisher struct{ fail bool }

func (publisher *membershipRelayPublisher) Publish(context.Context, membershipports.OutboxEvent) error {
	if publisher.fail {
		return errors.New("sink unavailable")
	}
	return nil
}

func TestMembershipOutboxRelayDoesNotAdvanceFailedSink(t *testing.T) {
	store := &membershipRelayStore{events: []membershipports.OutboxEvent{{
		EventID: "evt-1", EventType: "CircleMembershipJoined", Checkpoint: "1", OccurredAt: time.Now().UTC(),
	}}}
	publisher := &membershipRelayPublisher{fail: true}
	relay := NewOutboxRelay(store, store, publisher, "circle-member-count")
	if _, err := relay.Drain(context.Background(), 10); err == nil {
		t.Fatal("failed sink must be surfaced")
	}
	if store.checkpoint != "" {
		t.Fatalf("failed sink advanced checkpoint to %q", store.checkpoint)
	}
	publisher.fail = false
	if count, err := relay.Drain(context.Background(), 10); err != nil || count != 1 {
		t.Fatalf("retry count=%d err=%v", count, err)
	}
	if store.checkpoint != "1" {
		t.Fatalf("checkpoint=%q want=1", store.checkpoint)
	}
}
