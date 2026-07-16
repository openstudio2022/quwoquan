package application

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
)

type WorkService struct {
	works           userrepo.UserWorkReader
	creatorProfiles userrepo.CreatorRuntimeProfileReader
}

type WorkServiceOption func(*WorkService)

func WithCreatorRuntimeWorks(repository userrepo.CreatorRuntimeProfileReader) WorkServiceOption {
	return func(service *WorkService) {
		service.creatorProfiles = repository
	}
}

func NewWorkService(works userrepo.UserWorkReader, options ...WorkServiceOption) *WorkService {
	service := &WorkService{works: works}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
}

func (s *WorkService) ListUserWorks(ctx context.Context, userID, cursor string, limit int) ([]model.UserWork, string, error) {
	works, nextCursor, err := s.works.ListByUserID(ctx, userID, cursor, limit)
	if err != nil || len(works) > 0 || s.creatorProfiles == nil {
		return works, nextCursor, err
	}
	creatorWorks, found, err := s.creatorProfiles.ListActiveWorks(ctx, userID)
	if err != nil || !found {
		return works, nextCursor, err
	}
	if limit <= 0 {
		limit = 20
	}
	start := 0
	if cursor != "" {
		start = len(creatorWorks)
		for index := range creatorWorks {
			if creatorWorks[index].Ref == cursor {
				start = index + 1
				break
			}
		}
	}
	end := start + limit
	if end > len(creatorWorks) {
		end = len(creatorWorks)
	}
	result := make([]model.UserWork, 0, end-start)
	for _, work := range creatorWorks[start:end] {
		result = append(result, model.UserWork{
			ID: work.Ref, UserID: userID, Title: work.Title,
			CoverURL: work.CoverURL, WorkType: work.WorkType,
			RefID: work.Ref, SortOrder: work.SortOrder,
		})
	}
	nextCursor = ""
	if end < len(creatorWorks) && len(result) > 0 {
		nextCursor = result[len(result)-1].ID
	}
	return result, nextCursor, nil
}
