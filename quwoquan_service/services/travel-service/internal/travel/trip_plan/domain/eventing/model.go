package eventing

import (
	"context"
	"errors"
	"time"
)

var (
	ErrInvalidEvent     = errors.New("invalid Travel event")
	ErrOutboxConflict   = errors.New("Travel outbox delivery conflict")
	ErrInvalidTransport = errors.New("Travel event transport is unavailable")
)

type Event struct {
	Source           string
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          map[string]any
	OccurredAt       time.Time
}

type ClaimedEvent struct {
	Event
	ClaimedBy string
}

type OutboxStore interface {
	ClaimPending(context.Context, string, time.Time, time.Duration, int) ([]ClaimedEvent, error)
	MarkPublished(context.Context, ClaimedEvent, string, time.Time) error
	ReleaseClaims(context.Context, string, []ClaimedEvent) error
}

type Publisher interface {
	Publish(context.Context, Event) error
}

type Projection interface {
	Apply(context.Context, SourceEvent) error
}

type SourceEvent struct {
	EventID   string
	EventType string
	TripID    string
}
