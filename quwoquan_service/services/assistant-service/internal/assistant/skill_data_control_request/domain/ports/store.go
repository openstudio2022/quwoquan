package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
)

var ErrOutboxClaimLost = errors.New("skill data control outbox claim lost")

// OutboxEvent is the bounded publication envelope owned by
// SkillDataControlRequest. Payload contains only the fields declared for the
// concrete lifecycle event; worker lease and execution-fence state never
// crosses this boundary.
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	AttemptCount     int
}

// TransactionalOutbox is deliberately separate from Store: command and
// worker use cases cannot gain delivery authority merely by depending on the
// aggregate mutation port.
type TransactionalOutbox interface {
	ClaimPendingOutbox(
		context.Context,
		string,
		time.Time,
		time.Duration,
	) (OutboxEvent, bool, error)
	MarkOutboxPublished(context.Context, string, string, time.Time) error
	ScheduleOutboxRetry(
		context.Context, string, string, time.Time, time.Time, string,
	) error
}

type Store interface {
	Create(context.Context, model.CreateCommand) (model.MutationResult, error)
	Confirm(context.Context, model.ConfirmCommand) (model.MutationResult, error)
	Get(context.Context, string, string) (model.Request, error)
	ClaimNextExecution(context.Context, string, time.Time, time.Duration) (model.ExecutionClaim, bool, error)
	HeartbeatExecution(context.Context, model.ExecutionFence, time.Time, time.Duration) (model.ExecutionFence, error)
	MarkActionCompleted(context.Context, model.ExecutionFence, string, int64, time.Time) (model.Request, error)
	MarkCompleted(context.Context, model.ExecutionFence, int64, time.Time) (model.Request, error)
	MarkFailed(context.Context, model.ExecutionFence, string, string, int64, time.Time) (model.Request, error)
	ListSkillDataControlActivities(context.Context, string, string, int) ([]model.ActivityEvent, error)
}
