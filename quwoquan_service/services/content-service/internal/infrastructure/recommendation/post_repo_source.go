package recommendation

import (
	"context"
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type PostRepositorySource struct {
	store persistence.PostRepository
}

func NewPostRepositorySource(store persistence.PostRepository) *PostRepositorySource {
	return &PostRepositorySource{store: store}
}

func (s *PostRepositorySource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	posts := s.store.ListPublished(ctx, limit, req.Cursor)
	out := make([]rtrec.ContentCandidate, 0, len(posts))
	for _, p := range posts {
		out = append(out, rtrec.ContentCandidate{
			ContentID:    p.ID,
			ContentType:  p.ContentType,
			AuthorID:     p.AuthorId,
			Title:        p.Title,
			Tags:         candidateTagsFromAny(p.Tags),
			PublishedAt:  p.PublishedAt,
			ViewCount:    p.ViewCount,
			LikeCount:    p.LikeCount,
			CommentCount: p.CommentCount,
			ShareCount:   p.ShareCount,
		})
	}
	return out, nil
}

func (s *PostRepositorySource) GetByID(ctx context.Context, id string) (*postmodel.Post, bool) {
	return s.store.FindByID(ctx, id)
}

func (s *PostRepositorySource) ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post {
	return s.store.ListPublished(ctx, limit, cursor)
}

func candidateTagsFromAny(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			if s, ok := item.(string); ok && strings.TrimSpace(s) != "" {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}
