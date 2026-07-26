package command

import (
	"context"
	"fmt"
	"strings"
	"time"

	shareports "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/outboxrelay"
)

type OutboxRelay struct {
	reader      shareports.OutboxReader
	checkpoints shareports.ProjectionCheckpointStore
	publisher   shareports.OutboxPublisher
	consumer    string
	supervisor  *outboxrelay.Supervisor
}

func NewOutboxRelay(
	reader shareports.OutboxReader,
	checkpoints shareports.ProjectionCheckpointStore,
	publisher shareports.OutboxPublisher,
	consumer string,
) *OutboxRelay {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "content-outbound-share-runtime-events"
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
		return 0, fmt.Errorf("OutboundShareFact outbox relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load OutboundShareFact checkpoint: %w", err)
	}
	events, err := r.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read OutboundShareFact outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("OutboundShareFact event %q has no checkpoint", event.EventID)
		}
		if err := r.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish OutboundShareFact event %q: %w", event.EventID, err)
		}
		if err := r.checkpoints.SaveCheckpoint(ctx, r.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save OutboundShareFact checkpoint: %w", err)
		}
	}
	return len(events), nil
}

func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("OutboundShareFact outbox relay is not configured")
	}
	return r.supervisor.Run(ctx, interval, func(scanCtx context.Context) (int, error) {
		return r.Drain(scanCtx, 100)
	})
}

func (r *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("OutboundShareFact outbox relay is not configured")
	}
	return r.supervisor.Healthy(maxStaleness)
}
