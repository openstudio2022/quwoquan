package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type ProfileRepository interface {
	FindByID(ctx context.Context, userID string) (*model.UserProfile, error)
	FindByNickname(ctx context.Context, nickname string) (*model.UserProfile, error)
	Create(ctx context.Context, profile *model.UserProfile) error
	Update(ctx context.Context, profile *model.UserProfile) error
	IncrementCounter(ctx context.Context, userID, field string, delta int64) error
}
