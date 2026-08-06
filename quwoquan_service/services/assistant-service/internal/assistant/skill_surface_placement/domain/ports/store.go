package ports

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
)

var ErrOutboxClaimLost = errors.New("skill surface placement outbox claim lost")

// OutboxEvent is the metadata-approved SkillSurfacePlacementChanged payload
// that has already committed with the aggregate mutation.
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	AttemptCount     int
}

// TransactionalOutbox is deliberately separate from Store so local contract
// doubles for command/query behavior do not acquire a production relay seam.
type TransactionalOutbox interface {
	ClaimPendingOutbox(context.Context, string, time.Time, time.Duration) (OutboxEvent, bool, error)
	MarkOutboxPublished(context.Context, string, string, time.Time) error
	ScheduleOutboxRetry(context.Context, string, string, time.Time, string) error
}

type Reader interface {
	Get(context.Context, string, string) (model.Placement, error)
}

type Store interface {
	Reader
	Apply(context.Context, model.Command) (model.MutationResult, error)
}
