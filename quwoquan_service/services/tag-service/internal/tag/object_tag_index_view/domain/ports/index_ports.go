package ports

import (
	"context"
	"time"

	model "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/model"
)

type Reader interface {
	FindByObject(ctx context.Context, objectID, objectType string) (*model.ObjectTagIndex, error)
	FindObjectsByTagRef(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error)
	FindObjectsByTagRefSubtree(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error)
}

type Projector interface {
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
	ApplyUserProfileTagProjection(context.Context, UserProfileTagProjection) (bool, error)
}
