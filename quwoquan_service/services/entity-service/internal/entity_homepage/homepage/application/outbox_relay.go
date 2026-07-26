package homepage

import (
	"context"
	"fmt"

	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

const LifecycleStreamConsumer = "entity.homepage-lifecycle-stream"

type LifecycleOutboxSource interface {
	homepageports.OutboxReader
	homepageports.ProjectionCheckpointStore
}

type LifecycleOutboxRelay struct {
	source    LifecycleOutboxSource
	publisher homepageports.OutboxPublisher
}

func NewLifecycleOutboxRelay(
	source LifecycleOutboxSource,
	publisher homepageports.OutboxPublisher,
) (*LifecycleOutboxRelay, error) {
	if source == nil || publisher == nil {
		return nil, fmt.Errorf("homepage lifecycle relay requires source and publisher")
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
