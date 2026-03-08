package cache

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

const (
	circleCacheKeyPrefix = "cache:circle:"
	circleCacheTTL       = 600 * time.Second
)

// CachedCircleStore wraps a CircleStore with a Redis caching layer.
// Cache is invalidated on write operations per storage.yaml invalidation rules.
type CachedCircleStore struct {
	inner persistence.CircleStore
	rdb   redis.Cmdable
}

func NewCachedCircleStore(inner persistence.CircleStore, rdb redis.Cmdable) *CachedCircleStore {
	return &CachedCircleStore{inner: inner, rdb: rdb}
}

func (s *CachedCircleStore) cacheKey(id string) string {
	return fmt.Sprintf("%s%s", circleCacheKeyPrefix, id)
}

func (s *CachedCircleStore) invalidate(ctx context.Context, id string) {
	s.rdb.Del(ctx, s.cacheKey(id))
}

func (s *CachedCircleStore) FindByID(ctx context.Context, id string) (*model.Circle, bool) {
	key := s.cacheKey(id)
	data, err := s.rdb.Get(ctx, key).Bytes()
	if err == nil {
		var c model.Circle
		if json.Unmarshal(data, &c) == nil {
			return &c, true
		}
	}

	c, ok := s.inner.FindByID(ctx, id)
	if !ok {
		return nil, false
	}

	if encoded, err := json.Marshal(c); err == nil {
		s.rdb.Set(ctx, key, encoded, circleCacheTTL)
	}
	return c, true
}

func (s *CachedCircleStore) Create(ctx context.Context, circle *model.Circle) error {
	return s.inner.Create(ctx, circle)
}

func (s *CachedCircleStore) Update(ctx context.Context, id string, circle *model.Circle) bool {
	ok := s.inner.Update(ctx, id, circle)
	if ok {
		s.invalidate(ctx, id)
	}
	return ok
}

func (s *CachedCircleStore) List(ctx context.Context, opts persistence.ListCirclesOpts) ([]model.Circle, string) {
	return s.inner.List(ctx, opts)
}

func (s *CachedCircleStore) Archive(ctx context.Context, id string) bool {
	ok := s.inner.Archive(ctx, id)
	if ok {
		s.invalidate(ctx, id)
	}
	return ok
}

func (s *CachedCircleStore) IncrementMemberCount(ctx context.Context, id string, delta int64) error {
	err := s.inner.IncrementMemberCount(ctx, id, delta)
	if err == nil {
		s.invalidate(ctx, id)
	}
	return err
}

func (s *CachedCircleStore) UpdateStorageUsed(ctx context.Context, id string, deltaBytes int64) error {
	err := s.inner.UpdateStorageUsed(ctx, id, deltaBytes)
	if err == nil {
		s.invalidate(ctx, id)
	}
	return err
}

func (s *CachedCircleStore) UpdateSections(ctx context.Context, id string, sections []model.CircleSectionConfig) error {
	err := s.inner.UpdateSections(ctx, id, sections)
	if err == nil {
		s.invalidate(ctx, id)
	}
	return err
}
