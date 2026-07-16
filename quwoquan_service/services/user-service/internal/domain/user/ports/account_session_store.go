package ports

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type AccountSessionStore interface {
	FindByID(ctx context.Context, ownerID string) (*model.UserAuth, error)
	FindByRefreshToken(ctx context.Context, refreshToken string) (*model.UserAuth, error)
	UpsertRefreshToken(ctx context.Context, ownerID, refreshToken string, expiresAt time.Time) error
	RevokeRefreshToken(ctx context.Context, ownerID string) error
	RevokeRefreshTokenValue(ctx context.Context, refreshToken string) error
}
