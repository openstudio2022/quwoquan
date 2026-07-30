package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// CreatorRuntimeProfileReader 提供系统 creator 的运行时只读投影。
// 公共身份只认 immutable release authority 的 personaId，以及内容契约
// creatorProfileId 对应的 CreatorRuntimeProfile.creatorId；不接受 handle 或旧别名。
type CreatorRuntimeProfileReader interface {
	FindActiveByPublicIdentity(ctx context.Context, identity string) (*model.CreatorRuntimeProfile, bool, error)
	ListActiveWorks(ctx context.Context, identity string) ([]model.CreatorWorkRef, bool, error)
}
