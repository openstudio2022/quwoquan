package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
)

// CatalogSource 是 canonical skill manifest 与平台能力目录的唯一读取边界。
type CatalogSource interface {
	ListCatalogItems(context.Context) ([]model.Item, error)
}
