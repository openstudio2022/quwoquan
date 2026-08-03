package main

import (
	"context"

	circleapp "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	circlepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/circle/persistence"
	viewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
)

type circleSearchItemSnapshotReader struct {
	store *circlepersistence.MongoAggregateStore
}

func (reader circleSearchItemSnapshotReader) LoadSearchItem(
	ctx context.Context,
	circleID string,
) (viewapp.SearchItem, bool, error) {
	circle, found, err := reader.store.Load(ctx, circleID)
	if err != nil || !found || !circleapp.CircleSearchEligible(circle) {
		return viewapp.SearchItem{}, false, err
	}
	return viewapp.FromSearchDocument(
		circleapp.ProjectCircleToSearchDocument(circle), circle.Version,
	), true, nil
}

var _ viewapp.SnapshotReader = circleSearchItemSnapshotReader{}

type circleSearchItemEventSource struct {
	reader circleports.OutboxReader
}

func (source circleSearchItemEventSource) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]viewapp.LifecycleEvent, error) {
	events, err := source.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return nil, err
	}
	result := make([]viewapp.LifecycleEvent, 0, len(events))
	for _, event := range events {
		result = append(result, viewapp.LifecycleEvent{
			EventID: event.EventID, Type: event.EventType, CircleID: event.AggregateID,
			SourceVersion: event.AggregateVersion, Checkpoint: event.Checkpoint,
		})
	}
	return result, nil
}

var _ viewapp.EventSource = circleSearchItemEventSource{}
