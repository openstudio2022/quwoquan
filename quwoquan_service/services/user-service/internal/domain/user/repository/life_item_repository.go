package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type LifeItemRepository interface {
	ListByUserID(ctx context.Context, userID string, category string, cursor string, limit int) ([]model.UserLifeItem, string, error)
}
