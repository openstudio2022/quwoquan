package ports

import (
	"context"

	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

// TagNodeReader exposes the named taxonomy projection query contract.
type TagNodeReader interface {
	FindByReleaseAndTagRef(ctx context.Context, releaseID, tagRef string) (*model.TagNode, error)
	ListChildrenInRelease(ctx context.Context, releaseID, parentTagRef string, limit int64) ([]model.TagNode, error)
	CountUsableChildrenInRelease(ctx context.Context, releaseID, parentTagRef string) (int64, error)
	ListDimensionsInRelease(ctx context.Context, releaseID string) ([]model.TagNode, error)
	ListAllInRelease(ctx context.Context, releaseID string) ([]model.TagNode, error)
	IsUsableLeaf(ctx context.Context, releaseID, tagRef string) (bool, error)
}
