package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
)

var (
	ErrNotFound            = errors.New("trip plan placement not found")
	ErrCommitConflict      = errors.New("trip plan placement commit conflict")
	ErrIdempotencyConflict = errors.New("trip plan placement idempotency conflict")
	ErrSurfaceUnavailable  = errors.New("trip plan placement surface unavailable")
)

type CommandResult struct {
	Placement        model.Placement
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
	Placement       model.Placement
	Receipt         Receipt
	Event           OutboxEvent
}

type Store interface {
	Get(context.Context, string, model.SurfaceKind, string) (model.Placement, error)
	ListByTrip(context.Context, string) ([]model.Placement, error)
	ListActiveBySurface(context.Context, model.SurfaceKind, string) ([]model.Placement, error)
	FindReceipt(context.Context, string) (Receipt, bool, error)
	Commit(context.Context, Commit) error
}

type TripAuthority interface {
	OrganizerPersonaID(context.Context, string) (string, error)
}

type MembershipAuthority interface {
	CanViewTrip(context.Context, string, string) error
}

type SurfaceAuthority interface {
	RequireAdmin(context.Context, model.SurfaceKind, string, string, int64) error
	RequireMember(context.Context, model.SurfaceKind, string, string) error
}

type IDGenerator interface {
	NewTripPlanPlacementID() (string, error)
	NewEventID() (string, error)
}
