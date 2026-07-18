package persistence

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// PostStore is a minimal persistence store used by content-service.
// It keeps write/read semantics explicit so the service can evolve to Mongo later.
type PostStore struct {
	mu    sync.RWMutex
	posts map[string]postmodel.Post
}

func NewPostStore(seed []postmodel.Post) *PostStore {
	s := &PostStore{
		posts: make(map[string]postmodel.Post, len(seed)),
	}
	for _, p := range seed {
		cp := p
		s.posts[p.ID] = cp
	}
	return s
}

func (s *PostStore) FindByID(_ context.Context, id string) (*postmodel.Post, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	post, ok := s.posts[id]
	if !ok {
		return nil, false
	}
	cp := post
	return &cp, true
}

func (s *PostStore) FindByPublicationIntent(
	_ context.Context,
	authorID string,
	publishIntentID string,
) (*postmodel.Post, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, post := range s.posts {
		if post.AuthorId == strings.TrimSpace(authorID) &&
			post.PublishIntentId == strings.TrimSpace(publishIntentID) {
			cp := post
			return &cp, true
		}
	}
	return nil, false
}

func (s *PostStore) AdjustCommentCount(_ context.Context, id string, delta int64) (int64, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	post, ok := s.posts[id]
	if !ok {
		return 0, false, nil
	}
	post.CommentCount += delta
	post.UpdatedAt = time.Now().UTC()
	s.posts[id] = post
	return post.CommentCount, true, nil
}

func (s *PostStore) SetCommentCount(_ context.Context, id string, count int64) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	post, ok := s.posts[id]
	if !ok {
		return false, nil
	}
	post.CommentCount = count
	post.UpdatedAt = time.Now().UTC()
	s.posts[id] = post
	return true, nil
}

func (s *PostStore) ListAll(_ context.Context) ([]postmodel.Post, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	all := make([]postmodel.Post, 0, len(s.posts))
	for _, post := range s.posts {
		cp := post
		all = append(all, cp)
	}
	sort.Slice(all, func(i, j int) bool {
		return all[i].CreatedAt.After(all[j].CreatedAt)
	})
	return all, nil
}

func (s *PostStore) ListPublished(_ context.Context, limit int, cursor string) []postmodel.Post {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if limit <= 0 {
		limit = 20
	}
	all := make([]postmodel.Post, 0, len(s.posts))
	for _, p := range s.posts {
		if !strings.EqualFold(strings.TrimSpace(p.Status), "published") {
			continue
		}
		if !strings.EqualFold(strings.TrimSpace(p.Visibility), "public") {
			continue
		}
		all = append(all, p)
	}
	sort.Slice(all, func(i, j int) bool {
		return all[i].CreatedAt.After(all[j].CreatedAt)
	})
	if cursor != "" {
		start := 0
		for i, p := range all {
			if p.ID == cursor {
				start = i + 1
				break
			}
		}
		if start < len(all) {
			all = all[start:]
		} else {
			all = nil
		}
	}
	if len(all) > limit {
		all = all[:limit]
	}
	out := make([]postmodel.Post, 0, len(all))
	for _, p := range all {
		cp := p
		if cp.CreatedAt.IsZero() {
			cp.CreatedAt = time.Now().UTC()
		}
		out = append(out, cp)
	}
	return out
}

func (s *PostStore) ListByAuthor(_ context.Context, authorID string, limit int, cursor string) []postmodel.Post {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if limit <= 0 {
		limit = 20
	}
	all := make([]postmodel.Post, 0)
	for _, p := range s.posts {
		if p.AuthorId != authorID || !strings.EqualFold(strings.TrimSpace(p.Status), "published") {
			continue
		}
		all = append(all, p)
	}
	sort.Slice(all, func(i, j int) bool {
		return all[i].PublishedAt.After(all[j].PublishedAt)
	})
	if cursor != "" {
		start := 0
		for i, p := range all {
			if p.ID == cursor {
				start = i + 1
				break
			}
		}
		if start < len(all) {
			all = all[start:]
		} else {
			all = nil
		}
	}
	if len(all) > limit {
		all = all[:limit]
	}
	return all
}
