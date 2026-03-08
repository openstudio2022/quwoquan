package application

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
)

type LifeItemService struct {
	items userrepo.LifeItemRepository
}

func NewLifeItemService(items userrepo.LifeItemRepository) *LifeItemService {
	return &LifeItemService{items: items}
}

func (s *LifeItemService) ListUserLifeItems(ctx context.Context, userID, category, cursor string, limit int) ([]model.UserLifeItem, string, error) {
	return s.items.ListByUserID(ctx, userID, category, cursor, limit)
}
