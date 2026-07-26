package ports

import (
	"context"
	"encoding/json"
	"time"

	behaviorfactmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/domain/model"
)

type AppendRequest struct {
	Fact          behaviorfactmodel.CircleBehaviorFact
	CommandDigest string
}

type AppendReceipt struct {
	FactID   string
	Replayed bool
}

type AppendSink interface {
	Append(context.Context, AppendRequest) (AppendReceipt, error)
}

type CircleStateReader interface {
	ReadCircleState(context.Context, string) (string, bool, error)
}

type OutboxEvent struct {
	EventID     string
	EventType   string
	AggregateID string
	Payload     json.RawMessage
	OccurredAt  time.Time
	Checkpoint  string
}

type OutboxReader interface {
	ReadAfter(context.Context, string, int) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(context.Context, string) (string, error)
	SaveCheckpoint(context.Context, string, string) error
}

type OutboxPublisher interface {
	Publish(context.Context, OutboxEvent) error
}
