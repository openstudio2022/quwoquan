package ports

import (
	"context"
	"errors"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

var (
	// ErrPersonaHandleConflict 是基础设施在 user_handle 唯一约束冲突时返回的稳定领域语义。
	ErrPersonaHandleConflict = errors.New("persona handle conflict")
	// ErrPersonaPersistence 屏蔽具体数据库错误类型，避免 pgconn 等驱动错误穿透基础设施边界。
	ErrPersonaPersistence = errors.New("persona persistence failed")
	// ErrPersonaNotFound 表示原子状态切换时目标分身不存在或已不可激活。
	ErrPersonaNotFound = errors.New("persona not found")
)

type PersonaReader interface {
	FindByID(ctx context.Context, id string) (*model.Persona, error)
	FindByUserID(ctx context.Context, userID string) ([]model.Persona, error)
	FindActiveByUserID(ctx context.Context, userID string) (*model.Persona, error)
	FindByUserHandle(ctx context.Context, userHandle string) (*model.Persona, error)
	FindBySubAccountID(ctx context.Context, subAccountID string) (*model.Persona, error)
}

type PersonaWriter interface {
	Create(ctx context.Context, persona *model.Persona) error
	Update(ctx context.Context, persona *model.Persona) error
	Delete(ctx context.Context, id string) error
}

type PersonaHistoryReader interface {
	HasAttributedHistory(ctx context.Context, subAccountID string) (bool, error)
}

type PersonaActivationStore interface {
	SwitchActive(ctx context.Context, userID, subAccountID string) error
}
