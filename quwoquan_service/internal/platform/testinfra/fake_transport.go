package testinfra

import (
	"sync"
	"testing"

	"quwoquan_service/runtime/streaming"
)

type FakeStreamTransport struct {
	mu     sync.Mutex
	events []streaming.Envelope
}

func NewFakeStreamTransport() *FakeStreamTransport {
	return &FakeStreamTransport{}
}

func (t *FakeStreamTransport) Publish(event streaming.Envelope) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.events = append(t.events, event)
}

func (t *FakeStreamTransport) Events() []streaming.Envelope {
	t.mu.Lock()
	defer t.mu.Unlock()
	events := make([]streaming.Envelope, len(t.events))
	copy(events, t.events)
	return events
}

func (t *FakeStreamTransport) Last(tb testing.TB) streaming.Envelope {
	tb.Helper()
	t.mu.Lock()
	defer t.mu.Unlock()
	if len(t.events) == 0 {
		tb.Fatal("testinfra: fake stream transport has no events")
	}
	return t.events[len(t.events)-1]
}
