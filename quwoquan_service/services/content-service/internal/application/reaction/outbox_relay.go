package reaction

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/application/outboxrelay"
	reactionports "quwoquan_service/services/content-service/internal/domain/reaction/ports"
)

const defaultReactionOutboxConsumer = "content-reaction-runtime-events"

// OutboxRelay 是 ContentReaction transaction 之后唯一的事实投递路径。
type OutboxRelay struct {
	reader      reactionports.OutboxReader
	checkpoints reactionports.ProjectionCheckpointStore
	publisher   reactionports.OutboxPublisher
	consumer    string
	supervisor  *outboxrelay.Supervisor
}

func NewOutboxRelay(
	reader reactionports.OutboxReader,
	checkpoints reactionports.ProjectionCheckpointStore,
	publisher reactionports.OutboxPublisher,
	consumer string,
) *OutboxRelay {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = defaultReactionOutboxConsumer
	}
	return &OutboxRelay{
		reader:      reader,
		checkpoints: checkpoints,
		publisher:   publisher,
		consumer:    consumer,
		supervisor:  outboxrelay.NewSupervisor(consumer),
	}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.reader == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, fmt.Errorf("content reaction outbox relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load content reaction checkpoint: %w", err)
	}
	facts, err := r.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read content reaction outbox: %w", err)
	}
	for index, fact := range facts {
		if strings.TrimSpace(fact.Checkpoint) == "" {
			return index, fmt.Errorf("content reaction fact %q has no checkpoint", fact.EventID)
		}
		if err := r.publisher.Publish(ctx, fact); err != nil {
			return index, fmt.Errorf("publish content reaction fact %q: %w", fact.EventID, err)
		}
		if err := r.checkpoints.SaveCheckpoint(ctx, r.consumer, fact.Checkpoint); err != nil {
			return index, fmt.Errorf("save content reaction checkpoint for %q: %w", fact.EventID, err)
		}
	}
	return len(facts), nil
}

func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("content reaction outbox relay is not configured")
	}
	return r.supervisor.Run(ctx, interval, func(scanCtx context.Context) (int, error) {
		return r.Drain(scanCtx, 100)
	})
}

func (r *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("content reaction outbox relay is not configured")
	}
	return r.supervisor.Healthy(maxStaleness)
}
