package main

import (
	"context"

	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	gatheringexternal "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/external"
)

type gatheringCircleReader struct {
	circles circleports.AggregateStore
}

func (reader gatheringCircleReader) CircleExists(
	ctx context.Context,
	circleID string,
) (bool, error) {
	circle, found, err := reader.circles.Load(ctx, circleID)
	if err != nil || !found {
		return false, err
	}
	return string(circle.Status) == "active", nil
}

var _ gatheringexternal.LocalCircleReader = gatheringCircleReader{}
