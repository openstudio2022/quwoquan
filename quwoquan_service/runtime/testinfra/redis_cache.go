package testinfra

import (
	"context"
	"fmt"
	"time"

	"github.com/alicebob/miniredis/v2"
)

// MiniRedisCache implements repository.CacheAdapter using miniredis.
type MiniRedisCache struct {
	mr *miniredis.Miniredis
}

func NewMiniRedisCache(mr *miniredis.Miniredis) *MiniRedisCache {
	return &MiniRedisCache{mr: mr}
}

func (c *MiniRedisCache) Get(_ context.Context, key string) ([]byte, error) {
	val, err := c.mr.Get(key)
	if err != nil {
		return nil, fmt.Errorf("key %q not found", key)
	}
	return []byte(val), nil
}

func (c *MiniRedisCache) Set(_ context.Context, key string, value []byte, ttlSeconds int) error {
	if err := c.mr.Set(key, string(value)); err != nil {
		return err
	}
	if ttlSeconds > 0 {
		c.mr.SetTTL(key, time.Duration(ttlSeconds)*time.Second)
	}
	return nil
}

func (c *MiniRedisCache) Del(_ context.Context, key string) error {
	c.mr.Del(key)
	return nil
}
