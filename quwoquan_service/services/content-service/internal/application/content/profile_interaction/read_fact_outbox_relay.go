package profileinteraction

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/application/outboxrelay"
	readfactports "quwoquan_service/services/content-service/internal/domain/content/profile_interaction_read_fact/ports"
)

type ReadFactOutboxRelay struct {
	reader      readfactports.OutboxReader
	checkpoints readfactports.ProjectionCheckpointStore
	publisher   readfactports.OutboxPublisher
	consumer    string
	supervisor  *outboxrelay.Supervisor
}

func NewReadFactOutboxRelay(
	reader readfactports.OutboxReader,
	checkpoints readfactports.ProjectionCheckpointStore,
	publisher readfactports.OutboxPublisher,
	consumer string,
) *ReadFactOutboxRelay {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "content-profile-interaction-read-projection"
	}
	return &ReadFactOutboxRelay{
		reader: reader,
		checkpoints: checkpoints,
		publisher: publisher,
		consumer: consumer,
		supervisor: outboxrelay.NewSupervisor(consumer),
	}
}

func (r *ReadFactOutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.reader == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, fmt.Errorf("ProfileInteractionReadFact relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load ProfileInteractionReadFact checkpoint: %w", err)
	}
	events, err := r.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read ProfileInteractionReadFact outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("ProfileInteractionReadFact event %q has no checkpoint", event.EventID)
		}
		if err := r.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("project ProfileInteractionReadFact %q: %w", event.EventID, err)
		}
		if err := r.checkpoints.SaveCheckpoint(ctx, r.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save ProfileInteractionReadFact checkpoint: %w", err)
		}
	}
	return len(events), nil
}

func (r *ReadFactOutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("ProfileInteractionReadFact relay is not configured")
	}
	return r.supervisor.Run(ctx, interval, func(scanCtx context.Context) (int, error) {
		return r.Drain(scanCtx, 100)
	})
}

func (r *ReadFactOutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("ProfileInteractionReadFact relay is not configured")
	}
	return r.supervisor.Healthy(maxStaleness)
}
