package ports

import (
	"context"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
)

// TagNodeReader exposes the named taxonomy projection query contract.
type TagNodeReader interface {
	FindByTagRef(ctx context.Context, tagRef string) (*model.TagNode, error)
	ListChildren(ctx context.Context, parentTagRef string, limit int64) ([]model.TagNode, error)
	CountActiveChildren(ctx context.Context, parentTagRef string) (int64, error)
	ListAll(ctx context.Context) ([]model.TagNode, error)
}

// ObjectTagIndexReader exposes rebuildable object-to-tag index queries.
type ObjectTagIndexReader interface {
	FindByObject(ctx context.Context, objectID, objectType string) (*model.ObjectTagIndex, error)
	FindObjectsByTagRef(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error)
	FindObjectsByTagRefSubtree(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error)
}

// ObjectTagIndexProjector owns idempotent writes to the rebuildable index.
// Authoritative tagRefs remain on source aggregates.
type ObjectTagIndexProjector interface {
	UpsertObjectTags(ctx context.Context, objectID, objectType string, tagRefs []string) error
}
