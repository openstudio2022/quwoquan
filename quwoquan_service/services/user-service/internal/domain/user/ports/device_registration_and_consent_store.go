package ports

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

// DeviceRegistrationStore records login devices for owner accounts.
type DeviceRegistrationStore interface {
	UpsertLoginDevice(ctx context.Context, device *model.UserDevice) error
}

// ConsentRecord captures legal agreement acceptance at auth boundaries.
type ConsentRecord struct {
	ID               string
	OwnerID          string
	AgreementVersion string
	PrivacyVersion   string
	AcceptedAt       time.Time
	DeviceID         string
	Platform         string
	SourceOperation  string
}

type ConsentRecordStore interface {
	Create(ctx context.Context, record *ConsentRecord) error
}
