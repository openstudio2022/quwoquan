package repository

import (
	"context"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
)

// TagNodeReader 只读标签节点查询（resolve / shared-tags 标签富化）。
type TagNodeReader interface {
	FindByTagRef(ctx context.Context, tagRef string) (*model.TagNode, error)
}

// ObjectTagIndexReader 只读对象↔tagRef 索引查询（shared-tags / inverted）。
type ObjectTagIndexReader interface {
	FindByObject(ctx context.Context, objectID, objectType string) (*model.ObjectTagIndex, error)
	FindObjectsByTagRef(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error)
}
