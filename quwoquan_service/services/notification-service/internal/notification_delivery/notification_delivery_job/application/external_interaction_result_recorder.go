package application

import (
	"context"
	"errors"
	"time"

	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

// ExternalInteractionResultStore owns the transactional inbox, DeliveryJob CAS,
// and aggregate outbox write for one provider-result fact.
type ExternalInteractionResultStore interface {
	ApplyExternalInteractionResult(
		context.Context,
		notification.ExternalInteractionResultEvent,
		time.Time,
	) error
}

// ExternalInteractionResultRecorder is the application boundary consumed by
// stream adapters. Persistence remains an implementation detail of the port.
type ExternalInteractionResultRecorder interface {
	RecordExternalInteractionResult(
		context.Context,
		notification.ExternalInteractionResultEvent,
		time.Time,
	) error
}

type externalInteractionResultRecorder struct {
	store ExternalInteractionResultStore
}

func NewExternalInteractionResultRecorder(
	store ExternalInteractionResultStore,
) (ExternalInteractionResultRecorder, error) {
	if store == nil {
		return nil, errors.New("external interaction result recorder requires store")
	}
	return &externalInteractionResultRecorder{store: store}, nil
}

func (recorder *externalInteractionResultRecorder) RecordExternalInteractionResult(
	ctx context.Context,
	event notification.ExternalInteractionResultEvent,
	occurredAt time.Time,
) error {
	if recorder == nil || recorder.store == nil {
		return errors.New("external interaction result recorder is not configured")
	}
	return recorder.store.ApplyExternalInteractionResult(ctx, event, occurredAt)
}
