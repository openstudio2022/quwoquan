package homepage_review

import (
	"context"
	"fmt"
	"strings"

	reviewport "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
)

// OutboxRelay publishes HomepageReview facts to the canonical durable stream.
// Each consumer owns an independent checkpoint, so the local summary projector
// and external recommendation consumers cannot acknowledge one another's work.
type OutboxRelay struct {
	reader      reviewport.OutboxReader
	checkpoints reviewport.ProjectionCheckpointStore
	publisher   reviewport.OutboxPublisher
	consumer    string
}

func NewOutboxRelay(
	reader reviewport.OutboxReader,
	checkpoints reviewport.ProjectionCheckpointStore,
	publisher reviewport.OutboxPublisher,
	consumer string,
) (*OutboxRelay, error) {
	consumer = strings.TrimSpace(consumer)
	if reader == nil || checkpoints == nil || publisher == nil || consumer == "" {
		return nil, fmt.Errorf("HomepageReview outbox relay requires reader, checkpoint, publisher and consumer")
	}
	return &OutboxRelay{
		reader: reader, checkpoints: checkpoints,
		publisher: publisher, consumer: consumer,
	}, nil
}

func (relay *OutboxRelay) RunOnce(
	ctx context.Context,
	limit int,
) (int, error) {
	checkpoint, err := relay.checkpoints.LoadCheckpoint(ctx, relay.consumer)
	if err != nil {
		return 0, fmt.Errorf("load HomepageReview publication checkpoint: %w", err)
	}
	events, err := relay.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read HomepageReview outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.EventID) == "" {
			return index, fmt.Errorf("HomepageReview event has no checkpoint identity")
		}
		if err := relay.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish HomepageReview event %q: %w", event.EventID, err)
		}
		if err := relay.checkpoints.SaveCheckpoint(
			ctx,
			relay.consumer,
			event.EventID,
		); err != nil {
			return index, fmt.Errorf("save HomepageReview publication checkpoint: %w", err)
		}
	}
	return len(events), nil
}
