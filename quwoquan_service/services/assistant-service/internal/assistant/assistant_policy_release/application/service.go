package application

import (
	"context"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
)

type Store interface {
	Stage(
		ctx context.Context,
		release model.Release,
		commandID string,
	) (stored model.Release, replayed bool, err error)
	Get(
		ctx context.Context,
		policyID string,
		releaseVersion string,
	) (model.Release, bool, error)
}

type Service struct {
	store Store
	now   func() time.Time
}

type StageResult struct {
	Release  model.Release `json:"release"`
	Replayed bool          `json:"replayed"`
}

func NewService(store Store, now func() time.Time) *Service {
	if now == nil {
		now = time.Now
	}
	return &Service{store: store, now: now}
}

func (service *Service) Stage(
	ctx context.Context,
	commandID string,
	input model.Release,
) (StageResult, error) {
	if service == nil || service.store == nil ||
		strings.TrimSpace(commandID) == "" {
		return StageResult{}, model.ErrInvalidArgument
	}
	release, err := model.Stage(input, service.now())
	if err != nil {
		return StageResult{}, err
	}
	stored, replayed, err := service.store.Stage(
		ctx,
		release,
		strings.TrimSpace(commandID),
	)
	if err != nil {
		return StageResult{}, err
	}
	return StageResult{Release: stored, Replayed: replayed}, nil
}

func (service *Service) Get(
	ctx context.Context,
	policyID string,
	releaseVersion string,
) (model.Release, bool, error) {
	if service == nil || service.store == nil {
		return model.Release{}, false, model.ErrStorageUnavailable
	}
	return service.store.Get(
		ctx,
		strings.TrimSpace(policyID),
		strings.TrimSpace(releaseVersion),
	)
}
