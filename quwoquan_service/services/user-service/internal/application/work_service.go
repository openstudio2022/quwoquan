package application

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
)

type WorkService struct {
	works userrepo.WorkRepository
}

func NewWorkService(works userrepo.WorkRepository) *WorkService {
	return &WorkService{works: works}
}

func (s *WorkService) ListUserWorks(ctx context.Context, userID, cursor string, limit int) ([]model.UserWork, string, error) {
	return s.works.ListByUserID(ctx, userID, cursor, limit)
}
