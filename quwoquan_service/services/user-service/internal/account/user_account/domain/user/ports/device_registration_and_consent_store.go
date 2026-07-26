package ports

import (
	"context"
	"time"
)

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
