package transaction

import (
	"context"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

type Appender struct {
	application *application.Appender
}

func NewAppender(appender *application.Appender) *Appender {
	if appender == nil {
		panic("TripPlanRevision transaction adapter requires appender")
	}
	return &Appender{application: appender}
}

func (appender *Appender) AppendInTripPlanTransaction(ctx context.Context, revision model.Revision) error {
	return appender.application.Append(ctx, revision)
}
