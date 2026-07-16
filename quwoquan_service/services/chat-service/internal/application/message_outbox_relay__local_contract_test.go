package application

import (
	"context"
	"errors"
	"strconv"
	"testing"
	"time"
)

type messageOutboxRelayFixture struct {
	events      []MessageOutboxEvent
	checkpoint  string
	dispatched  map[string]bool
	published   []string
	failPublish bool
	failSave    bool
}

func (f *messageOutboxRelayFixture) ReadMessageOutboxAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]MessageOutboxEvent, error) {
	after := int64(0)
	if checkpoint != "" {
		after, _ = strconv.ParseInt(checkpoint, 10, 64)
	}
	result := make([]MessageOutboxEvent, 0, limit)
	for _, event := range f.events {
		sequence, _ := strconv.ParseInt(event.Checkpoint, 10, 64)
		if sequence > after {
			result = append(result, event)
		}
		if len(result) == limit {
			break
		}
	}
	return result, nil
}

func (f *messageOutboxRelayFixture) MarkMessageOutboxDispatched(
	_ context.Context,
	eventID string,
	_ time.Time,
) error {
	if f.dispatched == nil {
		f.dispatched = map[string]bool{}
	}
	f.dispatched[eventID] = true
	return nil
}

func (f *messageOutboxRelayFixture) LoadMessageOutboxCheckpoint(context.Context, string) (string, error) {
	return f.checkpoint, nil
}

func (f *messageOutboxRelayFixture) SaveMessageOutboxCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	if f.failSave {
		return errors.New("checkpoint unavailable")
	}
	f.checkpoint = checkpoint
	return nil
}

func (f *messageOutboxRelayFixture) PublishDomainEvent(
	context.Context,
	string,
	string,
	string,
	map[string]any,
) error {
	return nil
}

func (f *messageOutboxRelayFixture) PublishRecordedDomainEvent(
	_ context.Context,
	eventID string,
	_ string,
	_ string,
	_ string,
	_ map[string]any,
) error {
	if f.failPublish {
		return errors.New("transport unavailable")
	}
	f.published = append(f.published, eventID)
	return nil
}

func TestMessageOutboxRelayRetriesWithoutAdvancingCheckpoint(t *testing.T) {
	fixture := &messageOutboxRelayFixture{
		events: []MessageOutboxEvent{
			{EventID: "evt-1", EventType: "MessageSent", Checkpoint: "1"},
			{EventID: "evt-2", EventType: "AssistantMentioned", Checkpoint: "2"},
		},
		failPublish: true,
	}
	relay := NewMessageOutboxRelay(fixture, fixture, fixture, fixture, "test-consumer")

	if drained, err := relay.Drain(context.Background(), 10); err == nil || drained != 0 {
		t.Fatalf("failed publish should stop before checkpoint: drained=%d err=%v", drained, err)
	}
	if fixture.checkpoint != "" {
		t.Fatalf("checkpoint advanced on publish failure: %q", fixture.checkpoint)
	}

	fixture.failPublish = false
	drained, err := relay.Drain(context.Background(), 10)
	if err != nil || drained != 2 {
		t.Fatalf("retry drain = %d, %v; want 2, nil", drained, err)
	}
	if fixture.checkpoint != "2" || !fixture.dispatched["evt-1"] || !fixture.dispatched["evt-2"] {
		t.Fatalf("relay did not atomically advance durable delivery state: %#v", fixture)
	}
	if len(fixture.published) != 2 || fixture.published[0] != "evt-1" || fixture.published[1] != "evt-2" {
		t.Fatalf("published events = %#v", fixture.published)
	}
}

func TestMessageOutboxRelayReplaysStableEventAfterCheckpointFailure(t *testing.T) {
	fixture := &messageOutboxRelayFixture{
		events: []MessageOutboxEvent{{
			EventID:    "evt-stable",
			EventType:  "MessageSent",
			Checkpoint: "1",
		}},
		failSave: true,
	}
	relay := NewMessageOutboxRelay(fixture, fixture, fixture, fixture, "test-consumer")
	if _, err := relay.Drain(context.Background(), 10); err == nil {
		t.Fatal("expected checkpoint failure")
	}
	fixture.failSave = false
	if _, err := relay.Drain(context.Background(), 10); err != nil {
		t.Fatalf("replay after checkpoint recovery: %v", err)
	}
	if len(fixture.published) != 2 || fixture.published[0] != "evt-stable" || fixture.published[1] != "evt-stable" {
		t.Fatalf("replay must preserve event id for consumer dedupe: %#v", fixture.published)
	}
}
