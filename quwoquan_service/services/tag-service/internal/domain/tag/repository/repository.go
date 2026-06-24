package repository

import (
	"context"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
)

// TagNodeReader 只读标签节点查询（resolve / shared-tags 标签富化 / suggest）。
type TagNodeReader interface {
	FindByTagRef(ctx context.Context, tagRef string) (*model.TagNode, error)
	ListChildren(ctx context.Context, parentTagRef string, limit int64) ([]model.TagNode, error)
	CountActiveChildren(ctx context.Context, parentTagRef string) (int64, error)
	ListAll(ctx context.Context) ([]model.TagNode, error)
}

// ObjectTagIndexReader 只读对象↔tagRef 索引查询（shared-tags / inverted）。
type ObjectTagIndexReader interface {
	FindByObject(ctx context.Context, objectID, objectType string) (*model.ObjectTagIndex, error)
	FindObjectsByTagRef(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error)
}

// ObjectTagIndexWriter 写对象↔tagRef 倒排索引。
// 真相源仍是各源对象的 tagRefs（content.tagRefs / circle.tags / user.interestTags）；
// 本写入仅为派生倒排，幂等可重建（离线批量回填，事件增量为后续）。
type ObjectTagIndexWriter interface {
	UpsertObjectTags(ctx context.Context, objectID, objectType string, tagRefs []string) error
}
