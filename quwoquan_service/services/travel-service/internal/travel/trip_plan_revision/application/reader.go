package application

import (
	"context"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/ports"
)

type Reader struct {
	port ports.Reader
}

func NewReader(port ports.Reader) *Reader {
	if port == nil {
		panic("TripPlanRevision reader requires port")
	}
	return &Reader{port: port}
}

func (reader *Reader) Get(ctx context.Context, tripID string, number int64) (model.Revision, error) {
	if reader == nil || reader.port == nil || strings.TrimSpace(tripID) == "" || number <= 0 {
		return model.Revision{}, model.ErrInvalidRevision
	}
	return reader.port.Get(ctx, strings.TrimSpace(tripID), number)
}

// ValidateAssignment verifies that a Moment day/item target exists in the
// immutable revision named by the command. An empty itemID means a day-level
// assignment and still requires that the revision contains that day.
func (reader *Reader) ValidateAssignment(
	ctx context.Context,
	tripID string,
	number int64,
	dayIndex int,
	itemID string,
) error {
	if dayIndex < 0 {
		return model.ErrInvalidRevision
	}
	revision, err := reader.Get(ctx, tripID, number)
	if err != nil {
		return err
	}
	itemID = strings.TrimSpace(itemID)
	for _, item := range revision.Items {
		if item.DayIndex != dayIndex {
			continue
		}
		if itemID == "" || item.ItemID == itemID {
			return nil
		}
	}
	return model.ErrInvalidRevision
}
