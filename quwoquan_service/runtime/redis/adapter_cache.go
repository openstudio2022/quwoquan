package redis

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/runtime/repository"
)

// cacheAdapter bridges redis.Client → repository.CacheAdapter.
// Used by repository.Factory.WithCache() so that the unified Router
// can serve as the CacheAdapter backing for entity caching.
type cacheAdapter struct {
	client Client
}

// NewCacheAdapter wraps a redis.Client as a repository.CacheAdapter.
func NewCacheAdapter(client Client) repository.CacheAdapter {
	return &cacheAdapter{client: client}
}

func (a *cacheAdapter) Get(ctx context.Context, key string) ([]byte, error) {
	val, err := a.client.GetBytes(ctx, key)
	if errors.Is(err, ErrKeyNotFound) {
		return nil, nil
	}
	return val, err
}

func (a *cacheAdapter) Set(ctx context.Context, key string, value []byte, ttlSeconds int) error {
	ttl := time.Duration(ttlSeconds) * time.Second
	return a.client.SetBytes(ctx, key, value, ttl)
}

func (a *cacheAdapter) Del(ctx context.Context, key string) error {
	return a.client.Del(ctx, key)
}
