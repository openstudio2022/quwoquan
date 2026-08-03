package application

import (
	"context"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/ports"
)

type Appender struct {
	port ports.TransactionAppender
}

func NewAppender(port ports.TransactionAppender) *Appender {
	if port == nil {
		panic("TripPlanRevision appender requires port")
	}
	return &Appender{port: port}
}

func (appender *Appender) Append(
	ctx context.Context,
	revision model.Revision,
) error {
	if appender == nil || appender.port == nil {
		return model.ErrInvalidRevision
	}
	if err := revision.Validate(); err != nil {
		return err
	}
	return appender.port.AppendInTripPlanTransaction(ctx, revision)
}
