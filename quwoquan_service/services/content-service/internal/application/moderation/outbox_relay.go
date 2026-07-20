package moderation

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/application/outboxrelay"
	moderationports "quwoquan_service/services/content-service/internal/domain/moderation/ports"
)

const defaultModerationOutboxConsumer = "content-moderation-runtime-events"

// OutboxRelay 是 PostModerationCase 事实的唯一异步投递路径。它只读取已随
// aggregate transaction 提交的 outbox；命令请求不会在事务内 best-effort 发布。
type OutboxRelay struct {
	reader      moderationports.OutboxReader
	checkpoints moderationports.ProjectionCheckpointStore
	publisher   moderationports.OutboxPublisher
	consumer    string
	supervisor  *outboxrelay.Supervisor
}

func NewOutboxRelay(
	reader moderationports.OutboxReader,
	checkpoints moderationports.ProjectionCheckpointStore,
	publisher moderationports.OutboxPublisher,
	consumer string,
) *OutboxRelay {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = defaultModerationOutboxConsumer
	}
	return &OutboxRelay{
		reader: reader, checkpoints: checkpoints, publisher: publisher,
		consumer: consumer, supervisor: outboxrelay.NewSupervisor(consumer),
	}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.reader == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, fmt.Errorf("moderation outbox relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadModerationCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load moderation checkpoint: %w", err)
	}
	events, err := r.reader.ReadModerationOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read moderation outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("moderation event %q has no checkpoint", event.EventID)
		}
		if err := r.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish moderation event %q: %w", event.EventID, err)
		}
		if err := r.checkpoints.SaveModerationCheckpoint(ctx, r.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save moderation checkpoint for %q: %w", event.EventID, err)
		}
	}
	return len(events), nil
}

func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("moderation outbox relay is not configured")
	}
	return r.supervisor.Run(ctx, interval, func(scanCtx context.Context) (int, error) {
		return r.Drain(scanCtx, 100)
	})
}

func (r *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("moderation outbox relay is not configured")
	}
	return r.supervisor.Healthy(maxStaleness)
}
