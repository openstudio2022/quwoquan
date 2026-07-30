package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
)

// CatalogSource 是 canonical skill manifest 与平台能力目录的唯一读取边界。
type CatalogSource interface {
	ListCatalogItems(context.Context) ([]model.Item, error)
}

// ConsentReader 只暴露 SkillCatalog 需要的账号授权切片，避免目录对象依赖
// SkillConsent 的 Store 或持久化模型。
type ConsentReader interface {
	ListGrantedScopes(context.Context, string) (map[string]string, error)
}

type ConsentReaderFunc func(context.Context, string) (map[string]string, error)

func (read ConsentReaderFunc) ListGrantedScopes(
	ctx context.Context,
	accountID string,
) (map[string]string, error) {
	return read(ctx, accountID)
}
