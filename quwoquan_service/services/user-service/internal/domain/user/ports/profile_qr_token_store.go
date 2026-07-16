package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type ProfileQrTokenStore interface {
	FindByID(ctx context.Context, tokenID string) (*model.ProfileQrToken, error)
	FindActiveByOwnerAndHandle(ctx context.Context, ownerUserID, userHandle, styleVersion string) (*model.ProfileQrToken, error)
	FindByTokenHash(ctx context.Context, tokenHash string) (*model.ProfileQrToken, error)
	Create(ctx context.Context, token *model.ProfileQrToken) error
	Update(ctx context.Context, token *model.ProfileQrToken) error
}
