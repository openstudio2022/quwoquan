package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// CreatorRuntimeProfileReader 提供系统 creator 的运行时只读投影。
// 身份解析允许 creatorId、subAccountId 或 handle，供既有 profile API 透明消费。
type CreatorRuntimeProfileReader interface {
	FindActiveByIdentity(ctx context.Context, identity string) (*model.CreatorRuntimeProfile, bool, error)
	ListActiveWorks(ctx context.Context, identity string) ([]model.CreatorWorkRef, bool, error)
}
