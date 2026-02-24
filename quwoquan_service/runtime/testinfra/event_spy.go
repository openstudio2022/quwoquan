package testinfra

import (
	"context"
	"sync"

	"quwoquan_service/runtime/repository"
)

// EventSpy captures domain events published during tests.
type EventSpy struct {
	mu     sync.Mutex
	events []repository.DomainEvent
}

func NewEventSpy() *EventSpy {
	return &EventSpy{}
}

// Publish implements repository.EventPublisher.
func (s *EventSpy) Publish(_ context.Context, event repository.DomainEvent) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, event)
	return nil
}

// Events returns all captured events.
func (s *EventSpy) Events() []repository.DomainEvent {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]repository.DomainEvent, len(s.events))
	copy(out, s.events)
	return out
}

// EventsOfType returns events matching the given type.
func (s *EventSpy) EventsOfType(eventType string) []repository.DomainEvent {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []repository.DomainEvent
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
