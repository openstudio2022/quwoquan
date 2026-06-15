package persistence

import (
	"context"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	model "quwoquan_service/services/user-service/internal/domain/user/model"
	repository "quwoquan_service/services/user-service/internal/domain/user/repository"
)

type PgUserDeviceStore struct{ pgUserDeviceStoreBase }

var _ repository.UserDeviceRepository = (*PgUserDeviceStore)(nil)

func NewPgUserDeviceStore(pool *pgxpool.Pool) *PgUserDeviceStore {
	return &PgUserDeviceStore{pgUserDeviceStoreBase{pool: pool}}
}

func (s *PgUserDeviceStore) UpsertLoginDevice(ctx context.Context, device *model.UserDevice) error {
	if device == nil {
		return nil
	}
	now := time.Now().UTC()
	device.UserID = strings.TrimSpace(device.UserID)
	device.DeviceID = strings.TrimSpace(device.DeviceID)
	device.Platform = strings.TrimSpace(device.Platform)
	device.AppVersion = strings.TrimSpace(device.AppVersion)
	if device.UserID == "" || device.DeviceID == "" {
		return nil
	}
	if device.ID == "" {
		device.ID = "ud_" + device.UserID + "_" + device.DeviceID
	}
	if device.Platform == "" {
		device.Platform = "unknown"
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO user_devices (id, user_id, device_id, platform, push_token, app_version, last_active_at, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (user_id, device_id) DO UPDATE SET
			platform = EXCLUDED.platform,
			app_version = EXCLUDED.app_version,
			last_active_at = EXCLUDED.last_active_at
	`, device.ID, device.UserID, device.DeviceID, device.Platform, device.PushToken, device.AppVersion, now, now)
	return err
}
