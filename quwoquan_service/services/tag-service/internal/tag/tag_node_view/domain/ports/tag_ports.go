package ports

import (
	"context"
	"time"

	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

// TagNodeReader exposes the named taxonomy projection query contract.
type TagNodeReader interface {
	FindByReleaseAndTagRef(ctx context.Context, releaseID, tagRef string) (*model.TagNode, error)
	ListChildrenInRelease(ctx context.Context, releaseID, parentTagRef string, limit int64) ([]model.TagNode, error)
	CountActiveChildrenInRelease(ctx context.Context, releaseID, parentTagRef string) (int64, error)
	ListAllInRelease(ctx context.Context, releaseID string) ([]model.TagNode, error)
	IsActiveLeaf(ctx context.Context, releaseID, tagRef string) (bool, error)
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

type UserProfileTagProjection struct {
	EventID           string
	UserID            string
	TagRefs           []string
	TaxonomyReleaseID string
	ProfileVersion    int64
	OccurredAt        time.Time
}

type UserProfileTagProjector interface {
	ApplyUserProfileTagProjection(
		ctx context.Context,
		projection UserProfileTagProjection,
	) (applied bool, err error)
}
