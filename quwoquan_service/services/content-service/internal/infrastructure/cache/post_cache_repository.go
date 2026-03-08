package cache

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

const postCacheTTL = 300 * time.Second

// PostCacheRepository decorates a PostRepository with Redis read-through
// caching and write-invalidation. Redis failures are caught and degraded to
// direct DB reads so the service never blocks on cache unavailability.
type PostCacheRepository struct {
	inner  persistence.PostRepository
	redis  rtredis.Client
	logger *slog.Logger
}

func NewPostCacheRepository(inner persistence.PostRepository, redis rtredis.Client, logger *slog.Logger) *PostCacheRepository {
	if logger == nil {
		logger = slog.Default()
	}
	return &PostCacheRepository{inner: inner, redis: redis, logger: logger}
}

func (c *PostCacheRepository) cacheKey(id string) string {
	return fmt.Sprintf("cache:post:%s", id)
}

func (c *PostCacheRepository) Create(ctx context.Context, post *postmodel.Post) error {
	return c.inner.Create(ctx, post)
}

func (c *PostCacheRepository) Update(ctx context.Context, id string, post *postmodel.Post) bool {
	ok := c.inner.Update(ctx, id, post)
	if ok {
		if err := c.redis.Del(ctx, c.cacheKey(id)); err != nil {
			c.logger.Warn("cache invalidate failed", "key", c.cacheKey(id), "err", err)
		}
	}
	return ok
}

func (c *PostCacheRepository) FindByID(ctx context.Context, id string) (*postmodel.Post, bool) {
	key := c.cacheKey(id)

	data, err := c.redis.GetBytes(ctx, key)
	if err == nil && len(data) > 0 {
		var post postmodel.Post
		if json.Unmarshal(data, &post) == nil {
			return &post, true
		}
	}

	post, ok := c.inner.FindByID(ctx, id)
	if !ok {
		return nil, false
	}

	if encoded, err := json.Marshal(post); err == nil {
		if err := c.redis.SetBytes(ctx, key, encoded, postCacheTTL); err != nil {
			c.logger.Warn("cache fill failed", "key", key, "err", err)
		}
	}
	return post, true
}

func (c *PostCacheRepository) ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post {
	return c.inner.ListPublished(ctx, limit, cursor)
}

func (c *PostCacheRepository) ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post {
	return c.inner.ListByAuthor(ctx, authorID, limit, cursor)
}
