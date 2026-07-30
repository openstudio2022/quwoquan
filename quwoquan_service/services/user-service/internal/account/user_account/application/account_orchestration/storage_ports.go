package application

import (
	"context"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// PersonaStore 是 Persona 在 UserAccount 编排层的只读视图。所有写入必须经
// persona_management 的 PersonaCommandStore，禁止绕过 receipt/outbox。
type PersonaStore interface {
	userrepo.PersonaReader
}

// ProfileSnapshotCache 是完整用户资料快照的缓存端口。
type ProfileSnapshotCache interface {
	Get(ctx context.Context, userID string) (*model.FullSnapshot, error)
	Set(ctx context.Context, userID string, snapshot *model.FullSnapshot) error
	Del(ctx context.Context, userID string) error
}

// ProfileCacheInvalidator 供只需要失效资料缓存的命令服务使用。
type ProfileCacheInvalidator interface {
	Del(ctx context.Context, userID string) error
}

// BlockRelationshipCache 是拉黑关系集合的缓存端口。
type BlockRelationshipCache interface {
	IsMember(ctx context.Context, blockerID, blockedID string) (bool, error)
	Add(ctx context.Context, blockerID, blockedID string) error
	Remove(ctx context.Context, blockerID, blockedID string) error
	Exists(ctx context.Context, blockerID string) (bool, error)
	LoadFromDB(ctx context.Context, blockerID string, blockedIDs []string) error
}
