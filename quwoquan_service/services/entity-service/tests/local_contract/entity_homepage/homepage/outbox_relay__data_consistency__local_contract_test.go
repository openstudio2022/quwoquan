package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	"testing"

	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

type relaySourceStub struct {
	checkpoint string
	events     []homepageports.OutboxEvent
	saved      []string
}

func (source *relaySourceStub) LoadCheckpoint(
	context.Context,
	string,
) (string, error) {
	return source.checkpoint, nil
}

func (source *relaySourceStub) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]homepageports.OutboxEvent, error) {
	if checkpoint != source.checkpoint {
		return nil, errors.New("relay read from unexpected checkpoint")
	}
	return append([]homepageports.OutboxEvent(nil), source.events...), nil
}

func (source *relaySourceStub) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	source.saved = append(source.saved, checkpoint)
	return nil
}

type relayPublisherStub struct {
	failEventID string
	published   []string
}

func (publisher *relayPublisherStub) Publish(
	_ context.Context,
	event homepageports.OutboxEvent,
) error {
	if event.EventID == publisher.failEventID {
		return errors.New("stream unavailable")
	}
	publisher.published = append(publisher.published, event.EventID)
	return nil
}

func TestLifecycleOutboxRelayCheckpointsOnlyPublishedEvents(t *testing.T) {
	source := &relaySourceStub{
		checkpoint: "event-0",
		events: []homepageports.OutboxEvent{
			{EventID: "event-1"},
			{EventID: "event-2"},
		},
	}
	publisher := &relayPublisherStub{failEventID: "event-2"}
	relay, err := NewLifecycleOutboxRelay(source, publisher)
	if err != nil {
		t.Fatal(err)
	}

	processed, err := relay.RunOnce(context.Background(), 100)
	if err == nil {
		t.Fatal("publisher failure must stop the relay")
	}
	if processed != 1 {
		t.Fatalf("processed=%d want=1", processed)
	}
	if len(source.saved) != 1 || source.saved[0] != "event-1" {
		t.Fatalf("saved checkpoints=%v want=[event-1]", source.saved)
	}
	if len(publisher.published) != 1 || publisher.published[0] != "event-1" {
		t.Fatalf("published=%v want=[event-1]", publisher.published)
	}
}

func TestLifecycleOutboxRelayAdvancesThroughBatch(t *testing.T) {
	source := &relaySourceStub{
		events: []homepageports.OutboxEvent{
			{EventID: "event-1"},
			{EventID: "event-2"},
		},
	}
	publisher := &relayPublisherStub{}
	relay, err := NewLifecycleOutboxRelay(source, publisher)
	if err != nil {
		t.Fatal(err)
	}

	processed, err := relay.RunOnce(context.Background(), 100)
	if err != nil {
		t.Fatal(err)
	}
	if processed != 2 {
		t.Fatalf("processed=%d want=2", processed)
	}
	if len(source.saved) != 2 || source.saved[1] != "event-2" {
		t.Fatalf("saved checkpoints=%v want last event-2", source.saved)
	}
}
