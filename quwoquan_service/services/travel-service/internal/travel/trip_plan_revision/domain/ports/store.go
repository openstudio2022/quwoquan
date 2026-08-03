package ports

import (
	"context"
	"errors"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

var (
	ErrNotFound = errors.New("trip plan revision not found")
	ErrConflict = errors.New("trip plan revision conflict")
)

type Reader interface {
	Get(context.Context, string, int64) (model.Revision, error)
}

type TransactionAppender interface {
	AppendInTripPlanTransaction(context.Context, model.Revision) error
}

type Store interface {
	Reader
	TransactionAppender
}
