package ports

import (
	"context"
	"time"

	readfactmodel "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/model"
)

const EventTypeProfileInteractionReadFactAppended = "ProfileInteractionReadFactAppended"

type OutboxEvent struct {
	EventID    string
	EventType  string
	Payload    []byte
	OccurredAt time.Time
	Checkpoint string
}

type AppendRequest struct {
	Fact   readfactmodel.Fact
	Outbox OutboxEvent
}

type AppendResult struct {
	Fact     readfactmodel.Fact
	Replayed bool
}

type AppendSink interface {
	Append(context.Context, AppendRequest) (AppendResult, error)
}

type OutboxReader interface {
	ReadAfter(ctx context.Context, checkpoint string, limit int) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer string, checkpoint string) error
}

type OutboxPublisher interface {
	Publish(context.Context, OutboxEvent) error
}
