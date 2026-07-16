package application

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
)

type LifeItemService struct {
	items userrepo.UserLifeItemReader
}

func NewLifeItemService(items userrepo.UserLifeItemReader) *LifeItemService {
	return &LifeItemService{items: items}
}

func (s *LifeItemService) ListUserLifeItems(ctx context.Context, userID, category, cursor string, limit int) ([]model.UserLifeItem, string, error) {
	return s.items.ListByUserID(ctx, userID, category, cursor, limit)
}
