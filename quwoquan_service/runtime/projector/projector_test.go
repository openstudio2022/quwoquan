package projector

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"testing"

	"quwoquan_service/runtime/eventstore"
)

type mockProjector struct {
	name       string
	types      []string
	events     []eventstore.StoredEvent
	shouldFail bool
}

func (m *mockProjector) Name() string          { return m.name }
func (m *mockProjector) EventTypes() []string   { return m.types }
func (m *mockProjector) Project(_ context.Context, event eventstore.StoredEvent) error {
	if m.shouldFail {
		return fmt.Errorf("mock failure")
	}
	m.events = append(m.events, event)
	return nil
}

func TestDispatcher_RoutesToCorrectProjector(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	d := NewDispatcher(logger)

	feedProj := &mockProjector{name: "feed", types: []string{"PostCreated", "PostUpdated"}}
	chatProj := &mockProjector{name: "chat", types: []string{"MessageSent"}}

	d.Register(feedProj)
	d.Register(chatProj)

	// PostCreated → only feedProj
	err := d.Dispatch(context.Background(), eventstore.StoredEvent{
		Type:          "PostCreated",
		AggregateType: "Post",
		AggregateID:   "p1",
	})
	if err != nil {
		t.Fatal(err)
	}

	if len(feedProj.events) != 1 {
		t.Errorf("feedProj events: got %d, want 1", len(feedProj.events))
	}
	if len(chatProj.events) != 0 {
		t.Errorf("chatProj events: got %d, want 0", len(chatProj.events))
	}

	// MessageSent → only chatProj
	err = d.Dispatch(context.Background(), eventstore.StoredEvent{
		Type:          "MessageSent",
		AggregateType: "Message",
		AggregateID:   "m1",
	})
	if err != nil {
		t.Fatal(err)
	}

	if len(chatProj.events) != 1 {
		t.Errorf("chatProj events: got %d, want 1", len(chatProj.events))
	}
}

func TestDispatcher_MultipleProjectorsForSameEvent(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	d := NewDispatcher(logger)

	p1 := &mockProjector{name: "p1", types: []string{"PostCreated"}}
	p2 := &mockProjector{name: "p2", types: []string{"PostCreated"}}

	d.Register(p1)
	d.Register(p2)

	err := d.Dispatch(context.Background(), eventstore.StoredEvent{Type: "PostCreated"})
	if err != nil {
		t.Fatal(err)
	}

	if len(p1.events) != 1 || len(p2.events) != 1 {
		t.Errorf("both projectors should receive the event")
	}
}

func TestDispatcher_ProjectorFailure_ReturnsError(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	d := NewDispatcher(logger)

	failing := &mockProjector{name: "failing", types: []string{"X"}, shouldFail: true}
	d.Register(failing)

	err := d.Dispatch(context.Background(), eventstore.StoredEvent{Type: "X"})
	if err == nil {
		t.Error("expected error from failing projector")
	}
}

func TestDispatcher_ListProjectors(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	d := NewDispatcher(logger)

	d.Register(&mockProjector{name: "A", types: []string{"X"}})
	d.Register(&mockProjector{name: "B", types: []string{"X", "Y"}})

	names := d.ListProjectors()
	if len(names) != 2 {
		t.Errorf("ListProjectors: got %d, want 2", len(names))
	}
}
