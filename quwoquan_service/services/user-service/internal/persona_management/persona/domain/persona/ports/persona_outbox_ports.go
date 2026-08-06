package ports

import (
	"context"
	"errors"
	"time"
)

var ErrPersonaOutboxCheckpointLost = errors.New("Persona outbox checkpoint lost")

// PersonaOutboxEvent is the committed Persona fact read from personas_outbox.
// OwnerID is joined from the authoritative Persona row so the publisher can
// construct the exact userId/personaId contract instead of trusting old blobs.
type PersonaOutboxEvent struct {
	EventID          string
	OwnerID          string
	AggregateID      string
	AggregateVersion int64
	EventType        string
	PayloadJSON      []byte
	OccurredAt       time.Time
	AttemptCount     int
	ClaimUntil       time.Time
}

// PersonaPublicationOutbox owns retry and acknowledgement for the public
// Persona event stream. next_attempt_at doubles as a short claim lease because
// the existing canonical schema intentionally has no provider-specific owner.
type PersonaPublicationOutbox interface {
	ClaimPendingOutbox(context.Context, time.Time, time.Duration) (PersonaOutboxEvent, bool, error)
	MarkPublished(context.Context, string, time.Time, time.Time) error
	SchedulePublicationRetry(context.Context, string, time.Time, time.Time, string) error
}
