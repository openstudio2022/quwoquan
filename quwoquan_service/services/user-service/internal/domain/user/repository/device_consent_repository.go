package repository

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

// UserDeviceRepository records login devices for owner accounts.
type UserDeviceRepository interface {
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

type ConsentRepository interface {
	Create(ctx context.Context, record *ConsentRecord) error
}
