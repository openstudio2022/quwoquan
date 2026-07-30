package ports

import (
	"context"
	"errors"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
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
	FindByPersonaID(ctx context.Context, personaID string) (*model.Persona, error)
}

// PersonaOwnerAccountReader 是跨对象读取 Persona owner 的最窄 typed port。
// DeviceRegistration 来电 destination resolver 只需要 accountId，禁止为此加载
// Persona 全量私有字段或在 application 层直连 personas 表。
type PersonaOwnerAccountReader interface {
	ResolveOwnerAccountID(
		ctx context.Context,
		personaID string,
	) (accountID string, found bool, err error)
}
