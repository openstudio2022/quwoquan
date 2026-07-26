package persistence

import (
	"context"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	repository "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

type PgConsentRecordStore struct {
	pool *pgxpool.Pool
}

var _ repository.ConsentRecordStore = (*PgConsentRecordStore)(nil)

func NewPgConsentRecordStore(pool *pgxpool.Pool) *PgConsentRecordStore {
	return &PgConsentRecordStore{pool: pool}
}

func (s *PgConsentRecordStore) Create(ctx context.Context, record *repository.ConsentRecord) error {
	if s == nil || s.pool == nil || record == nil {
		return nil
	}
	record.OwnerID = strings.TrimSpace(record.OwnerID)
	record.AgreementVersion = strings.TrimSpace(record.AgreementVersion)
	record.PrivacyVersion = strings.TrimSpace(record.PrivacyVersion)
	record.SourceOperation = strings.TrimSpace(record.SourceOperation)
	if record.OwnerID == "" || record.AgreementVersion == "" || record.PrivacyVersion == "" {
		return nil
	}
	if record.ID == "" {
		record.ID = "cr_" + time.Now().UTC().Format("20060102150405.000000000")
	}
	if record.AcceptedAt.IsZero() {
		record.AcceptedAt = time.Now().UTC()
	}
	if record.SourceOperation == "" {
		record.SourceOperation = "LoginOneTap"
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO consent_records (
			id, owner_id, agreement_version, privacy_version, accepted_at, device_id, platform, source_operation
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`, record.ID, record.OwnerID, record.AgreementVersion, record.PrivacyVersion, record.AcceptedAt, record.DeviceID, record.Platform, record.SourceOperation)
	return err
}
