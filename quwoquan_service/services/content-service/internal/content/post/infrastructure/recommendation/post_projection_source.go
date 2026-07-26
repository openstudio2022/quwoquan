package recommendation

import (
	"context"
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
)

type PostProjectionSource struct {
	detail     postports.DetailReader
	collection postports.CollectionReader
}

func NewPostProjectionSource(
	detail postports.DetailReader,
	collection postports.CollectionReader,
) *PostProjectionSource {
	return &PostProjectionSource{detail: detail, collection: collection}
}

func (s *PostProjectionSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	posts := s.collection.ListPublished(ctx, limit, req.Cursor)
	out := make([]rtrec.ContentCandidate, 0, len(posts))
	for _, p := range posts {
		if postsemantic.Present(p.SemanticMentions) {
			projection := postsemantic.Project(p.SemanticMentions)
			p.TagRefs = projection.TagRefs
			p.EntityRefs = projection.EntityRefs
		}
		projection := BuildRecommendationProjectionFields(postProjectionPayload(p))
		contentVertical, _ := projection["contentVertical"].(string)
		if vertical := normalizedVertical(req.Vertical); vertical != "" && normalizedVertical(contentVertical) != vertical {
			continue
		}
		qualityScore, _ := projection["qualityScore"].(float64)
		supplySource, _ := projection["supplySource"].(string)
		out = append(out, rtrec.ContentCandidate{
			ContentID:       p.ID,
			ContentType:     p.ContentType,
			AuthorID:        p.AuthorId,
			Title:           p.Title,
			Tags:            candidateTagsFromAny(p.TagRefs),
			EntityRefs:      candidateTagsFromAny(p.EntityRefs),
			PublishedAt:     p.PublishedAt,
			ViewCount:       p.ViewCount,
			LikeCount:       p.LikeCount,
			CommentCount:    p.CommentCount,
			ShareCount:      p.ShareCount,
			QualityScore:    qualityScore,
			ContentVertical: contentVertical,
			SupplySource:    supplySource,
		})
	}
	return out, nil
}

func (s *PostProjectionSource) GetByID(ctx context.Context, id string) (*postmodel.Post, bool) {
	return s.detail.FindByID(ctx, id)
}

func (s *PostProjectionSource) ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post {
	return s.collection.ListPublished(ctx, limit, cursor)
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

func postProjectionPayload(p postmodel.Post) map[string]any {
	return map[string]any{
		"authorId":             p.AuthorId,
		"contentType":          p.ContentType,
		"tagRefs":              candidateTagsFromAny(p.TagRefs),
		"entityRefs":           candidateTagsFromAny(p.EntityRefs),
		"semanticMentions":     p.SemanticMentions,
		"contentVertical":      p.ContentVertical,
		"sourceTaskId":         p.SourceTaskId,
		"coverUrl":             p.CoverUrl,
		"thumbnailUrl":         p.ThumbnailUrl,
		"videoUrl":             p.VideoUrl,
		"mediaUrls":            p.MediaUrls,
		"authorQualitySignals": p.AuthorQualitySignals,
		"status":               p.Status,
		"visibility":           p.Visibility,
	}
}
