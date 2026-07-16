package testinfra

import (
	"context"
	"sync"

	messaging "quwoquan_service/runtime/messaging"
)

// EventSpy captures domain events published during tests.
type EventSpy struct {
	mu     sync.Mutex
	events []messaging.DomainEvent
}

func NewEventSpy() *EventSpy {
	return &EventSpy{}
}

// Publish implements messaging.EventPublisher.
func (s *EventSpy) Publish(_ context.Context, event messaging.DomainEvent) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, event)
	return nil
}

// Events returns all captured events.
func (s *EventSpy) Events() []messaging.DomainEvent {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]messaging.DomainEvent, len(s.events))
	copy(out, s.events)
	return out
}

// EventsOfType returns events matching the given type.
func (s *EventSpy) EventsOfType(eventType string) []messaging.DomainEvent {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []messaging.DomainEvent
	for _, e := range s.events {
		if e.Type == eventType {
			out = append(out, e)
		}
	}
	return out
}

// Reset clears all captured events.
func (s *EventSpy) Reset() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = nil
}

// Count returns total captured events.
func (s *EventSpy) Count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.events)
}
