package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type CredentialRepository interface {
	FindByOwner(ctx context.Context, ownerID string) ([]model.CredentialBinding, error)
	FindByTypeAndKey(ctx context.Context, credentialType, credentialKey string) (*model.CredentialBinding, error)
	FindByOwnerAndType(ctx context.Context, ownerID, credentialType string) (*model.CredentialBinding, error)
	Create(ctx context.Context, c *model.CredentialBinding) error
	Deactivate(ctx context.Context, ownerID, credentialType string) error
	CountActive(ctx context.Context, ownerID string) (int, error)
	UpdateLastUsed(ctx context.Context, id string) error
}
