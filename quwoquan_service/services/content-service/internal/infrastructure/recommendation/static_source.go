package recommendation

import (
	"context"
	"strings"
	"sync"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type StaticCandidateSource struct {
	mu    sync.RWMutex
	posts []postmodel.Post
	byID  map[string]postmodel.Post
}

func NewStaticCandidateSource() *StaticCandidateSource {
	posts := DefaultSeedPosts()
	byID := make(map[string]postmodel.Post, len(posts))
	for _, p := range posts {
		byID[p.ID] = p
	}
	return &StaticCandidateSource{posts: posts, byID: byID}
}

func DefaultSeedPosts() []postmodel.Post {
	now := time.Now().UTC()
	return []postmodel.Post{
		{ID: "post_micro_001", AuthorId: "user_1001", ContentType: "micro", Title: "Today in Hangzhou", Body: "City walk and coffee notes", Tags: []string{"city", "life"}, MediaUrls: []string{"https://picsum.photos/seed/micro1/800/600"}, LikeCount: 23, CommentCount: 4, FavoriteCount: 8, ShareCount: 2, CreatedAt: now.Add(-2 * time.Hour), PublishedAt: now.Add(-2 * time.Hour), Status: "published", Visibility: "public"},
		{ID: "post_photo_001", AuthorId: "user_1002", ContentType: "image", Title: "Winter light", Body: "Street photography set", Tags: []string{"photo", "street"}, MediaUrls: []string{"https://picsum.photos/seed/photo1/800/900"}, CoverUrl: "https://picsum.photos/seed/photo1/800/900", LikeCount: 103, CommentCount: 12, FavoriteCount: 39, ShareCount: 9, CreatedAt: now.Add(-4 * time.Hour), PublishedAt: now.Add(-4 * time.Hour), Status: "published", Visibility: "public"},
		{ID: "post_video_001", AuthorId: "user_1003", ContentType: "video", Title: "Night run vlog", Body: "Training route and pacing", Tags: []string{"video", "fitness"}, VideoUrl: "https://example.com/videos/night-run.mp4", CoverUrl: "https://picsum.photos/seed/video1/800/1200", LikeCount: 88, CommentCount: 20, FavoriteCount: 21, ShareCount: 13, CreatedAt: now.Add(-1 * time.Hour), PublishedAt: now.Add(-1 * time.Hour), Status: "published", Visibility: "public"},
		{ID: "post_article_001", AuthorId: "user_1004", ContentType: "article", Title: "How to structure deep work", Body: "A practical checklist for focused sessions", Tags: []string{"article", "productivity"}, CoverUrl: "https://picsum.photos/seed/article1/1200/700", LikeCount: 66, CommentCount: 15, FavoriteCount: 45, ShareCount: 11, CreatedAt: now.Add(-6 * time.Hour), PublishedAt: now.Add(-6 * time.Hour), Status: "published", Visibility: "public"},
	}
}

func (s *StaticCandidateSource) Recall(_ context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	limit := req.Limit
	if limit <= 0 || limit > len(s.posts) {
		limit = len(s.posts)
	}
	out := make([]rtrec.ContentCandidate, 0, limit)
	for _, p := range s.posts {
		out = append(out, rtrec.ContentCandidate{
			ContentID:    p.ID,
			ContentType:  p.ContentType,
			AuthorID:     p.AuthorId,
			Title:        p.Title,
			Tags:         toStringSlice(p.Tags),
			PublishedAt:  p.PublishedAt,
			ViewCount:    p.ViewCount,
			LikeCount:    p.LikeCount,
			CommentCount: p.CommentCount,
			ShareCount:   p.ShareCount,
		})
		if len(out) >= limit {
			break
		}
	}
	return out, nil
}

func (s *StaticCandidateSource) GetByID(id string) (*postmodel.Post, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	p, ok := s.byID[id]
	if !ok {
		return nil, false
	}
	cp := p
	return &cp, true
}

func toStringSlice(v any) []string {
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
