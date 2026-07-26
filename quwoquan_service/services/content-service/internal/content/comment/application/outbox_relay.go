package comment

import (
	"context"
	"fmt"
	"strings"
	"time"

	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/outboxrelay"
)

const defaultCommentOutboxConsumer = "content-comment-runtime-events"

type OutboxRelay struct {
	reader      commentports.OutboxReader
	checkpoints commentports.ProjectionCheckpointStore
	publisher   commentports.OutboxPublisher
	consumer    string
	supervisor  *outboxrelay.Supervisor
}

func NewOutboxRelay(
	reader commentports.OutboxReader,
	checkpoints commentports.ProjectionCheckpointStore,
	publisher commentports.OutboxPublisher,
	consumer string,
) *OutboxRelay {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = defaultCommentOutboxConsumer
	}
	return &OutboxRelay{
		reader: reader, checkpoints: checkpoints, publisher: publisher,
		consumer: consumer, supervisor: outboxrelay.NewSupervisor(consumer),
	}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.reader == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, fmt.Errorf("comment outbox relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load comment checkpoint: %w", err)
	}
	events, err := r.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read comment outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("comment event %q has no checkpoint", event.EventID)
		}
		if err := r.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish comment event %q: %w", event.EventID, err)
		}
		if err := r.checkpoints.SaveCheckpoint(ctx, r.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save comment checkpoint for %q: %w", event.EventID, err)
		}
	}
	return len(events), nil
}

func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("comment outbox relay is not configured")
	}
	return r.supervisor.Run(ctx, interval, func(scanCtx context.Context) (int, error) {
		return r.Drain(scanCtx, 100)
	})
}

func (r *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("comment outbox relay is not configured")
	}
	return r.supervisor.Healthy(maxStaleness)
}
