package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
)

var (
	ErrNotFound             = errors.New("trip moment not found")
	ErrCommitConflict       = errors.New("trip moment commit conflict")
	ErrIdempotencyConflict  = errors.New("trip moment idempotency conflict")
	ErrReferenceUnavailable = errors.New("trip moment reference unavailable")
)

type CommandResult struct {
	Moment           model.Moment
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
	Moment          model.Moment
	Receipt         Receipt
	Event           OutboxEvent
}

type Store interface {
	Get(context.Context, string, string) (model.Moment, error)
	ListActive(context.Context, string) ([]model.Moment, error)
	FindReceipt(context.Context, string) (Receipt, bool, error)
	Commit(context.Context, Commit) error
}

type MembershipAuthority interface {
	CanViewTrip(context.Context, string, string) error
}

type TripAuthority interface {
	OrganizerPersonaID(context.Context, string) (string, error)
}

type AssignmentAuthority interface {
	ValidateAssignment(context.Context, string, int64, int, string) error
}

type ReferenceAuthority interface {
	ValidateMomentReferences(context.Context, model.Kind, *model.ObjectRef, *model.ObjectRef, string) error
}

type IDGenerator interface {
	NewTripMomentID() (string, error)
	NewEventID() (string, error)
}
