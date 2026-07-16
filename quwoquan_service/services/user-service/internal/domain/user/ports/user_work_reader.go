package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type UserWorkReader interface {
	ListByUserID(ctx context.Context, userID string, cursor string, limit int) ([]model.UserWork, string, error)
}
