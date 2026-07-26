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
	FindBySubAccountID(ctx context.Context, subAccountID string) (*model.Persona, error)
}

// PersonaOwnerAccountReader 是跨对象读取 Persona owner 的最窄 typed port。
// DeviceRegistration 来电 destination resolver 只需要 accountId，禁止为此加载
// Persona 全量私有字段或在 application 层直连 personas 表。
type PersonaOwnerAccountReader interface {
	ResolveOwnerAccountID(
		ctx context.Context,
		subAccountID string,
	) (accountID string, found bool, err error)
}

// PersonaWriter 只服务两类非公开命令写入：登录 bootstrap 首建 Persona，
// 以及 owner 基线资料向 active Persona 的展示字段传播（version 单调由
// personas 表触发器承载）。公开 Persona 命令一律经
// persona_management/persona/domain/ports.PersonaCommandStore 原子提交
// state/receipt/outbox，不得回退到本端口。
type PersonaWriter interface {
	Create(ctx context.Context, persona *model.Persona) error
	Update(ctx context.Context, persona *model.Persona) error
}
