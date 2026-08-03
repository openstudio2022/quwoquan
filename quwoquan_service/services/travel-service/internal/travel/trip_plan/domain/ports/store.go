package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

var (
	ErrNotFound            = errors.New("trip plan not found")
	ErrCommitConflict      = errors.New("trip plan commit conflict")
	ErrIdempotencyConflict = errors.New("trip command idempotency conflict")
)

type CommandResult struct {
	TripID                string
	Version               int64
	CurrentRevisionID     string
	CurrentRevisionNumber int64
	Status                model.Status
	IdempotentReplay      bool
}

type CommandReceipt struct {
	IdempotencyKey string
	CommandDigest  string
	Result         CommandResult
	ExpiresAt      time.Time
}

type ListQuery struct {
	OrganizerPersonaID string
	Status             model.Status
	Cursor             string
	Limit              int
}

type PlanPage struct {
	Plans      []model.Plan
	NextCursor string
}

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          map[string]any
	OccurredAt       time.Time
}

type ClaimedOutboxEvent struct {
	OutboxEvent
	ClaimedBy string
}

type Commit struct {
	ExpectedPlanVersion    int64
	ExpectedRevisionNumber int64
	Plan                   model.Plan
	Revision               revisionmodel.Revision
	Receipt                CommandReceipt
	Event                  OutboxEvent
	RevisionEvent          OutboxEvent
}

type Store interface {
	GetPlan(context.Context, string) (model.Plan, error)
	ListPlans(context.Context, ListQuery) (PlanPage, error)
	FindReceipt(context.Context, string) (CommandReceipt, bool, error)
	Commit(context.Context, Commit) error
}

type OutboxStore interface {
	ClaimPendingOutbox(
		context.Context,
		string,
		time.Time,
		time.Duration,
		int,
	) ([]ClaimedOutboxEvent, error)
	MarkOutboxPublished(context.Context, string, string, time.Time) error
	ReleaseOutboxClaims(context.Context, string, []string) error
}

type EventPublisher interface {
	Publish(context.Context, OutboxEvent) error
}
