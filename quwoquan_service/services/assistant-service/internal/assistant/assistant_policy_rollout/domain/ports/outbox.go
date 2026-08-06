package ports

import (
	"context"
	"errors"
	"time"
)

var ErrOutboxClaimLost = errors.New("assistant policy rollout outbox claim lost")

// OutboxEvent is the immutable AssistantPolicyRollout event recorded in the
// same MongoDB transaction as the aggregate revision. Payload is the exact
// object-contract payload; delivery lease state never crosses this boundary.
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int
	OccurredAt       time.Time
	Payload          []byte
	AttemptCount     int
}

// TransactionalOutbox separates delivery authority from the aggregate Store.
// A publisher must own the current lease to retry or acknowledge an event.
type TransactionalOutbox interface {
	ClaimPendingOutbox(
		context.Context,
		string,
		time.Time,
		time.Duration,
	) (OutboxEvent, bool, error)
	MarkOutboxPublished(context.Context, string, string, string, time.Time) error
	ScheduleOutboxRetry(
		context.Context, string, string, time.Time, time.Time, string,
	) error
}
