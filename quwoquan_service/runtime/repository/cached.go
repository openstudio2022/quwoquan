package repository

import (
	"context"
	"encoding/json"
	"fmt"
)

// cachedRepository wraps a Repository with cache read-through and invalidation.
type cachedRepository struct {
	inner      Repository[map[string]any]
	cache      CacheAdapter
	entityName string
	ttl        int
}

// NewCachedRepository decorates a repository with caching.
func NewCachedRepository(
	inner Repository[map[string]any],
	cache CacheAdapter,
	entityName string,
	ttlSeconds int,
) CacheableRepository[map[string]any] {
	return &cachedRepository{
		inner:      inner,
		cache:      cache,
		entityName: entityName,
		ttl:        ttlSeconds,
	}
}

func (c *cachedRepository) cacheKey(id string) string {
	return fmt.Sprintf("cache:%s:%s", c.entityName, id)
}

func (c *cachedRepository) FindByID(ctx context.Context, id string) (*map[string]any, error) {
	return c.inner.FindByID(ctx, id)
}

func (c *cachedRepository) FindByIDCached(ctx context.Context, id string) (*map[string]any, error) {
	key := c.cacheKey(id)

	data, err := c.cache.Get(ctx, key)
	if err == nil && len(data) > 0 {
		var result map[string]any
		if json.Unmarshal(data, &result) == nil {
			return &result, nil
		}
	}

	entity, err := c.inner.FindByID(ctx, id)
	if err != nil {
		return nil, err
	}
	if entity == nil {
		return nil, nil
	}

	if encoded, err := json.Marshal(entity); err == nil {
		_ = c.cache.Set(ctx, key, encoded, c.ttl)
	}

	return entity, nil
}

func (c *cachedRepository) InvalidateCache(ctx context.Context, id string) error {
	return c.cache.Del(ctx, c.cacheKey(id))
}

func (c *cachedRepository) FindAll(ctx context.Context, q Query) (*Page[map[string]any], error) {
	return c.inner.FindAll(ctx, q)
}

func (c *cachedRepository) Create(ctx context.Context, entity *map[string]any) error {
	return c.inner.Create(ctx, entity)
}

func (c *cachedRepository) Update(ctx context.Context, id string, entity *map[string]any) error {
	if err := c.inner.Update(ctx, id, entity); err != nil {
		return err
	}
	_ = c.InvalidateCache(ctx, id)
	return nil
}

func (c *cachedRepository) Delete(ctx context.Context, id string) error {
	if err := c.inner.Delete(ctx, id); err != nil {
		return err
	}
	_ = c.InvalidateCache(ctx, id)
	return nil
}

func (c *cachedRepository) Count(ctx context.Context, filter Filter) (int64, error) {
	return c.inner.Count(ctx, filter)
}
