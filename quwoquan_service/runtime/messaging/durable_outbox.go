package runtimemessaging

import (
	"context"
	"time"
)

// LeasedDurableOutboxEvent is an object-owned event that was atomically
// recorded with its aggregate change and leased for durable publication.
// Payload must be a redacted, serialized event document; its schema remains
// owned by the emitting object.
type LeasedDurableOutboxEvent struct {
	ID               string
	EventType        string
	AggregateType    string
	AggregateID      string
	AggregateVersion int
	OccurredAt       time.Time
	Payload          string
}

// LeasedDurableOutboxStore lets an object-owned persistence adapter coordinate
// a lease with the shared durable transport without exposing its storage model.
type LeasedDurableOutboxStore interface {
	ClaimPendingOutbox(
		context.Context,
		string,
		time.Duration,
		int,
	) ([]LeasedDurableOutboxEvent, error)
	MarkOutboxPublished(context.Context, string, string, string, time.Time) error
	ReleaseOutboxClaim(context.Context, string, string) error
}
