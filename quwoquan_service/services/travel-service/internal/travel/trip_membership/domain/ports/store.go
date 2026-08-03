package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
)

var (
	ErrNotFound            = errors.New("trip membership not found")
	ErrCommitConflict      = errors.New("trip membership commit conflict")
	ErrIdempotencyConflict = errors.New("trip membership idempotency conflict")
	ErrSourceUnavailable   = errors.New("trip membership source unavailable")
)

type CommandResult struct {
	Membership       model.Membership
	IdempotentReplay bool
}

type Receipt struct {
	IdempotencyKey string
	CommandDigest  string
	Result         CommandResult
	ExpiresAt      time.Time
}

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          map[string]any
	OccurredAt       time.Time
}

type Commit struct {
	ExpectedVersion int64
	Membership      model.Membership
	Receipt         Receipt
	Event           OutboxEvent
}

type Store interface {
	Get(context.Context, string, string) (model.Membership, error)
	List(context.Context, string) ([]model.Membership, error)
	FindReceipt(context.Context, string) (Receipt, bool, error)
	Commit(context.Context, Commit) error
}

type TripAuthority interface {
	OrganizerPersonaID(context.Context, string) (string, error)
}

type SourceAuthority interface {
	ValidateMembershipSource(context.Context, model.SourceKind, *model.SourceRef, int64, string) error
}

type IDGenerator interface {
	NewTripMembershipID() (string, error)
	NewEventID() (string, error)
}
