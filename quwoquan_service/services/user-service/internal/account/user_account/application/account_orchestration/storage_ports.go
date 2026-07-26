package application

import (
	"context"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// PersonaStore 组合分身读写能力；事务切换与历史查询保持独立端口。
type PersonaStore interface {
	userrepo.PersonaReader
	userrepo.PersonaWriter
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
