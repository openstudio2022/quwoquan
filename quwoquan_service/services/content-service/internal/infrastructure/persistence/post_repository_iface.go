package persistence

import (
	"context"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// PostRepository defines the minimal storage operations used by the application
// layer. Both PostStore (in-memory) and MongoPostStore implement this interface.
type PostRepository interface {
	Create(ctx context.Context, post *postmodel.Post) error
	Update(ctx context.Context, id string, post *postmodel.Post) bool
	FindByID(ctx context.Context, id string) (*postmodel.Post, bool)
	ListAll(ctx context.Context) []postmodel.Post
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
	ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post
	// AdjustCommentCount atomically applies delta to the post's denormalized
	// commentCount accelerator (hot path: single-field $inc, no CountDocuments
	// scan and no full-document rewrite) and returns the new value. The
	// authoritative source remains the comments collection count; this field is
	// a feed/detail accelerator that self-heals via SetCommentCount.
	AdjustCommentCount(ctx context.Context, postID string, delta int64) (int64, bool, error)
	// SetCommentCount atomically sets the denormalized commentCount to the
	// authoritative value (drift self-heal; single $set, no full rewrite).
	SetCommentCount(ctx context.Context, postID string, count int64) (bool, error)
}
