package application

import (
	"context"
	"strings"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
)

type Service struct {
	store ports.Store
	now   func() time.Time
	newID func() string
}

func NewService(
	store ports.Store,
	now func() time.Time,
	newID func() string,
) *Service {
	if store == nil {
		panic("skill data control store is required")
	}
	if now == nil {
		now = time.Now
	}
	if newID == nil {
		newID = uuid.NewString
	}
	return &Service{store: store, now: now, newID: newID}
}

func (service *Service) Create(
	ctx context.Context,
	accountID string,
	skillID string,
	actions []string,
	idempotencyKey string,
) (model.MutationResult, error) {
	request, err := model.NewRequest(
		service.newID(), accountID, skillID, actions, service.now(),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	command, err := model.NewCreateCommand(request, idempotencyKey)
	if err != nil {
		return model.MutationResult{}, err
	}
	return service.store.Create(ctx, command)
}

func (service *Service) Get(
	ctx context.Context,
	accountID string,
	requestID string,
) (model.Request, error) {
	if strings.TrimSpace(accountID) == "" || strings.TrimSpace(requestID) == "" {
		return model.Request{}, model.ErrInvalidArgument
	}
	return service.store.Get(ctx, strings.TrimSpace(accountID), strings.TrimSpace(requestID))
}

func (service *Service) Confirm(
	ctx context.Context,
	accountID string,
	requestID string,
	expectedRevision int64,
	confirmed bool,
	idempotencyKey string,
) (model.MutationResult, error) {
	command, err := model.NewConfirmCommand(
		accountID,
		requestID,
		expectedRevision,
		confirmed,
		idempotencyKey,
		service.now(),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	result, err := service.store.Confirm(ctx, command)
	return result, err
}
