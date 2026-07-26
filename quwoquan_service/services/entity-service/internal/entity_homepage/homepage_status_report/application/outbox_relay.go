package homepage_status_report

import (
	"context"
	"fmt"

	statusports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/domain/ports"
)

const LifecycleStreamConsumer = "entity.homepage-status-lifecycle-stream"

type LifecycleOutboxSource interface {
	statusports.OutboxReader
	statusports.ProjectionCheckpointStore
}

type LifecycleOutboxRelay struct {
	source    LifecycleOutboxSource
	publisher statusports.OutboxPublisher
}

func NewLifecycleOutboxRelay(
	source LifecycleOutboxSource,
	publisher statusports.OutboxPublisher,
) (*LifecycleOutboxRelay, error) {
	if source == nil || publisher == nil {
		return nil, fmt.Errorf("homepage status lifecycle relay requires source and publisher")
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
