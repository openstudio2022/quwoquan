package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
)

var (
	ErrNotFound             = errors.New("trip plan template not found")
	ErrCommitConflict       = errors.New("trip plan template commit conflict")
	ErrIdempotencyConflict  = errors.New("trip plan template idempotency conflict")
	ErrReferenceUnavailable = errors.New("trip plan template reference unavailable")
)

type CommandResult struct {
	Template         model.Template
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
	Template        model.Template
	Receipt         Receipt
	Event           OutboxEvent
}

type Store interface {
	Get(context.Context, string) (model.Template, error)
	ListByOwner(context.Context, string) ([]model.Template, error)
	FindReceipt(context.Context, string) (Receipt, bool, error)
	Commit(context.Context, Commit) error
}

type ReferenceAuthority interface {
	ValidateTemplateAttributions(context.Context, string, []model.Attribution) error
}
type IDGenerator interface {
	NewTripPlanTemplateID() (string, error)
	NewEventID() (string, error)
}
