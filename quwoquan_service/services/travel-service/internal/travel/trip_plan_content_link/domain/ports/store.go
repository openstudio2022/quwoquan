package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
)

var (
	ErrNotFound            = errors.New("trip plan content link not found")
	ErrCommitConflict      = errors.New("trip plan content link commit conflict")
	ErrIdempotencyConflict = errors.New("trip plan content link idempotency conflict")
	ErrPostUnavailable     = errors.New("trip plan content link post unavailable")
)

type CommandResult struct {
	Link             model.Link
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
	Link            model.Link
	Receipt         Receipt
	Event           OutboxEvent
}

type Store interface {
	Get(context.Context, string, string) (model.Link, error)
	ListActive(context.Context, string) ([]model.Link, error)
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

type PostAuthority interface {
	ValidateVisiblePost(context.Context, string, string, model.Visibility) error
}

type IDGenerator interface {
	NewTripPlanContentLinkID() (string, error)
	NewEventID() (string, error)
}
