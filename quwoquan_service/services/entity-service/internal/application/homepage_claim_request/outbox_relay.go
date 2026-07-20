package homepage_claim_request

import (
	"context"
	"fmt"

	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
)

const LifecycleStreamConsumer = "entity.homepage-claim-lifecycle-stream"

type LifecycleOutboxSource interface {
	claimports.OutboxReader
	claimports.ProjectionCheckpointStore
}

type LifecycleOutboxRelay struct {
	source    LifecycleOutboxSource
	publisher claimports.OutboxPublisher
}

func NewLifecycleOutboxRelay(
	source LifecycleOutboxSource,
	publisher claimports.OutboxPublisher,
) (*LifecycleOutboxRelay, error) {
	if source == nil || publisher == nil {
		return nil, fmt.Errorf("homepage claim lifecycle relay requires source and publisher")
	}
	return &LifecycleOutboxRelay{source: source, publisher: publisher}, nil
}

func (relay *LifecycleOutboxRelay) RunOnce(
	ctx context.Context,
	limit int,
) (int, error) {
	checkpoint, err := relay.source.LoadCheckpoint(ctx, LifecycleStreamConsumer)
	if err != nil {
		return 0, err
	}
	events, err := relay.source.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, err
	}
	for index, event := range events {
		if err := relay.publisher.Publish(ctx, event); err != nil {
			return index, err
		}
		if err := relay.source.SaveCheckpoint(
			ctx,
			LifecycleStreamConsumer,
			event.EventID,
		); err != nil {
			return index, err
		}
	}
	return len(events), nil
}
