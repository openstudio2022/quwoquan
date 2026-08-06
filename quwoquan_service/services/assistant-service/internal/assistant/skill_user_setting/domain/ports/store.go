package ports

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
)

var ErrOutboxClaimLost = errors.New("skill user setting outbox claim lost")

// OutboxEvent contains only the contract-approved setting projection. Raw
// configuration_data never crosses the publication boundary.
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	AttemptCount     int
}

// TransactionalOutbox is separate from Store so command/query doubles cannot
// be mistaken for a production publication adapter.
type TransactionalOutbox interface {
	ClaimPendingOutbox(context.Context, string, time.Time, time.Duration) (OutboxEvent, bool, error)
	MarkOutboxPublished(context.Context, string, string, time.Time) error
	ScheduleOutboxRetry(context.Context, string, string, time.Time, string) error
}

type Reader interface {
	Get(context.Context, string, string) (model.Setting, error)
	List(context.Context, string, int) ([]model.Setting, error)
}

type Store interface {
	Reader
	Apply(context.Context, model.Command) (model.MutationResult, error)
}
