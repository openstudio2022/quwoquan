package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type UserSettingsStore interface {
	FindByUserID(ctx context.Context, userID string) (*model.UserSetting, error)
	Upsert(ctx context.Context, setting *model.UserSetting) error
}
