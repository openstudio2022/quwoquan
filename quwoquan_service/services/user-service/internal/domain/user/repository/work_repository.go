package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type WorkRepository interface {
	ListByUserID(ctx context.Context, userID string, cursor string, limit int) ([]model.UserWork, string, error)
}
