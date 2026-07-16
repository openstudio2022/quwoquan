package post

import (
	"context"
	"errors"
	"testing"
	"time"

	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

type relayReader struct {
	events []postports.OutboxEvent
}

func (r relayReader) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]postports.OutboxEvent, error) {
	start := 0
	if checkpoint != "" {
		for index, event := range r.events {
			if event.Checkpoint == checkpoint {
				start = index + 1
				break
			}
		}
	}
	return append([]postports.OutboxEvent(nil), r.events[start:]...), nil
}

type relayCheckpoints struct {
	checkpoint string
}

func (s *relayCheckpoints) LoadCheckpoint(_ context.Context, _ string) (string, error) {
	return s.checkpoint, nil
}

func (s *relayCheckpoints) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	s.checkpoint = checkpoint
	return nil
}

type relayPublisher struct {
	published []string
	failEvent string
}

func (p *relayPublisher) Publish(_ context.Context, event postports.OutboxEvent) error {
	if event.EventID == p.failEvent {
		return errors.New("simulated publish failure")
	}
	p.published = append(p.published, event.EventID)
	return nil
}

func TestOutboxRelayAdvancesCheckpointOnlyAfterPublish(t *testing.T) {
	t.Parallel()

	checkpoints := &relayCheckpoints{}
	publisher := &relayPublisher{}
	relay := NewOutboxRelay(
		relayReader{events: []postports.OutboxEvent{
			{
				EventID:    "event-1",
				Checkpoint: "checkpoint-1",
				OccurredAt: time.Now().UTC(),
			},
			{
				EventID:    "event-2",
				Checkpoint: "checkpoint-2",
				OccurredAt: time.Now().UTC(),
			},
		}},
		checkpoints,
		publisher,
		"test-consumer",
	)

	delivered, err := relay.Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("Drain() error = %v", err)
	}
	if delivered != 2 {
		t.Fatalf("Drain() delivered = %d, want 2", delivered)
	}
	if checkpoints.checkpoint != "checkpoint-2" {
		t.Fatalf("checkpoint = %q, want checkpoint-2", checkpoints.checkpoint)
	}
}

func TestOutboxRelayDoesNotAdvanceFailedEventCheckpoint(t *testing.T) {
	t.Parallel()

	checkpoints := &relayCheckpoints{}
	publisher := &relayPublisher{failEvent: "event-2"}
	relay := NewOutboxRelay(
		relayReader{events: []postports.OutboxEvent{
			{EventID: "event-1", Checkpoint: "checkpoint-1"},
			{EventID: "event-2", Checkpoint: "checkpoint-2"},
		}},
		checkpoints,
		publisher,
		"test-consumer",
	)

	delivered, err := relay.Drain(context.Background(), 10)
	if err == nil {
		t.Fatal("Drain() must report a publisher failure")
	}
	if delivered != 1 {
		t.Fatalf("Drain() delivered = %d, want 1", delivered)
	}
	if checkpoints.checkpoint != "checkpoint-1" {
		t.Fatalf("checkpoint = %q, want checkpoint-1", checkpoints.checkpoint)
	}
}

func TestOutboxRelayHealthRequiresRecentSuccessfulScan(t *testing.T) {
	t.Parallel()

	relay := NewOutboxRelay(
		relayReader{},
		&relayCheckpoints{},
		&relayPublisher{},
		"test-consumer",
	)
	if err := relay.Healthy(time.Second); err == nil {
		t.Fatal("Healthy() must reject a relay without a completed scan")
	}

	relay.recordSuccess()
	if err := relay.Healthy(time.Second); err != nil {
		t.Fatalf("Healthy() after successful scan = %v", err)
	}
	relay.recordFailure(errors.New("broker unavailable"))
	if err := relay.Healthy(time.Second); err == nil {
		t.Fatal("Healthy() must expose a newer delivery failure")
	}
}
