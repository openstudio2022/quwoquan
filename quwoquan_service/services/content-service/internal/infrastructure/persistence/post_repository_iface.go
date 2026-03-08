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
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
	ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post
}
