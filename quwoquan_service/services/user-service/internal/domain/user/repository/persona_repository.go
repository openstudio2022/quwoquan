package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type PersonaRepository interface {
	FindByID(ctx context.Context, id string) (*model.Persona, error)
	FindByUserID(ctx context.Context, userID string) ([]model.Persona, error)
	FindActiveByUserID(ctx context.Context, userID string) (*model.Persona, error)
	FindByUserHandle(ctx context.Context, userHandle string) (*model.Persona, error)
	FindBySubAccountID(ctx context.Context, subAccountID string) (*model.Persona, error)
	HasAttributedHistory(ctx context.Context, subAccountID string) (bool, error)
	Create(ctx context.Context, persona *model.Persona) error
	Update(ctx context.Context, persona *model.Persona) error
	Delete(ctx context.Context, id string) error
	DeactivateAll(ctx context.Context, userID string) error
	ActivateOne(ctx context.Context, id string) error
}
