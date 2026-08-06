package application

import (
	"context"
	"errors"
	"strings"
	"time"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// PersonaProfileProjector 是 UserAccount 对 Persona lifecycle 事件的唯一
// application facet。底层 port 负责持久化与 checkpoint；本 facet 统一执行
// 事件坐标校验，并被 API、release import 与恢复 runner 共同消费。
type PersonaProfileProjector struct {
	projection userports.PersonaProfileProjector
}

func NewPersonaProfileProjector(
	projection userports.PersonaProfileProjector,
) (*PersonaProfileProjector, error) {
	if projection == nil {
		return nil, errors.New("Persona profile projection port is required")
	}
	return &PersonaProfileProjector{projection: projection}, nil
}

func (projector *PersonaProfileProjector) Project(
	ctx context.Context,
	personaID string,
	aggregateVersion int64,
) (*usermodel.UserProfile, error) {
	if projector == nil || projector.projection == nil {
		return nil, errors.New("Persona profile projector is not configured")
	}
	if strings.TrimSpace(personaID) == "" || aggregateVersion <= 0 {
		return nil, errors.New("Persona profile projection requires identity and aggregate version")
	}
	return projector.projection.Project(ctx, strings.TrimSpace(personaID), aggregateVersion)
}

func (projector *PersonaProfileProjector) ProjectNext(
	ctx context.Context,
) (bool, error) {
	if projector == nil || projector.projection == nil {
		return false, errors.New("Persona profile projector is not configured")
	}
	return projector.projection.ProjectNext(ctx)
}

func (projector *PersonaProfileProjector) Run(
	ctx context.Context,
	interval time.Duration,
) error {
	if projector == nil || projector.projection == nil {
		return errors.New("Persona profile projector is not configured")
	}
	if interval <= 0 {
		return errors.New("Persona profile projector interval must be positive")
	}
	return projector.projection.Run(ctx, interval)
}

var _ userports.PersonaProfileProjector = (*PersonaProfileProjector)(nil)
