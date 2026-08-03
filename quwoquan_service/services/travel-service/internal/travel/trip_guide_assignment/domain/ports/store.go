package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
)

var (
	ErrNotFound             = errors.New("trip guide assignment not found")
	ErrCommitConflict       = errors.New("trip guide assignment commit conflict")
	ErrIdempotencyConflict  = errors.New("trip guide assignment idempotency conflict")
	ErrReferenceUnavailable = errors.New("trip guide assignment reference unavailable")
)

type CommandResult struct {
	Assignment       model.Assignment
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
	Assignment      model.Assignment
	Receipt         Receipt
	Event           OutboxEvent
}

type Store interface {
	Get(context.Context, string, string) (model.Assignment, error)
	ListByTrip(context.Context, string) ([]model.Assignment, error)
	FindReceipt(context.Context, string) (Receipt, bool, error)
	Commit(context.Context, Commit) error
}
type TripAuthority interface {
	OrganizerPersonaID(context.Context, string) (string, error)
}
type MembershipAuthority interface {
	CanViewTrip(context.Context, string, string) error
}
type PersonaAuthority interface {
	ValidateGuidePersona(context.Context, string, string, model.Role) error
}
type IDGenerator interface {
	NewTripGuideAssignmentID() (string, error)
	NewEventID() (string, error)
}
