package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
	"testing"
	"time"

	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

type placementRelayStore struct {
	events     []placementports.OutboxEvent
	checkpoint string
}

func (store *placementRelayStore) ReadAfter(_ context.Context, checkpoint string, _ int) ([]placementports.OutboxEvent, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return store.events, nil
}

func (store *placementRelayStore) LoadCheckpoint(context.Context, string) (string, error) {
	return store.checkpoint, nil
}

func (store *placementRelayStore) SaveCheckpoint(_ context.Context, _ string, checkpoint string) error {
	store.checkpoint = checkpoint
	return nil
}

type placementRelayPublisher struct{ fail bool }

func (publisher *placementRelayPublisher) Publish(context.Context, placementports.OutboxEvent) error {
	if publisher.fail {
		return errors.New("sink unavailable")
	}
	return nil
}

func TestPlacementOutboxRelayDoesNotAdvanceFailedSink(t *testing.T) {
	store := &placementRelayStore{events: []placementports.OutboxEvent{{
		EventID: "evt-1", EventType: "CirclePostPlaced", Checkpoint: "1", OccurredAt: time.Now().UTC(),
	}}}
	publisher := &placementRelayPublisher{fail: true}
	relay := NewOutboxRelay(store, store, publisher, "circle-feed")
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
