package persistence

import (
	"context"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgAnonymousDeviceBindingStore extends pgAnonymousDeviceBindingStoreBase with lookup helpers.
type PgAnonymousDeviceBindingStore struct {
	pgAnonymousDeviceBindingStoreBase
}

var _ repository.AnonymousDeviceBindingRepository = (*PgAnonymousDeviceBindingStore)(nil)

func NewPgAnonymousDeviceBindingStore(pool *pgxpool.Pool) *PgAnonymousDeviceBindingStore {
	return &PgAnonymousDeviceBindingStore{pgAnonymousDeviceBindingStoreBase{pool: pool}}
}

func (s *PgAnonymousDeviceBindingStore) FindByDeviceFingerprintHash(
	ctx context.Context,
	deviceFingerprintHash string,
) (*model.AnonymousDeviceBinding, error) {
	return scanAnonymousDeviceBinding(s.pool.QueryRow(
		ctx,
		`SELECT `+anonymousDeviceBindingCols+` FROM anonymous_device_bindings WHERE device_fingerprint_hash = $1`,
		strings.TrimSpace(deviceFingerprintHash),
	))
}

func (s *PgAnonymousDeviceBindingStore) Touch(
	ctx context.Context,
	id, installIDHash, platform, appVersion string,
) error {
	now := time.Now().UTC()
	normalizedPlatform := strings.TrimSpace(platform)
	if normalizedPlatform == "" {
		normalizedPlatform = "unknown"
	}
	_, err := s.pool.Exec(
		ctx,
		`UPDATE anonymous_device_bindings
		 SET install_id_hash = $2,
		     platform = $3,
		     app_version = $4,
		     last_seen_at = $5,
		     updated_at = $5
		 WHERE id = $1`,
		strings.TrimSpace(id),
		strings.TrimSpace(installIDHash),
		normalizedPlatform,
		strings.TrimSpace(appVersion),
		now,
	)
	return err
}
