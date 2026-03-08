package cache

import "github.com/redis/go-redis/v9"

// NewMiniredisClient creates a redis.Client suitable for miniredis in tests.
func NewMiniredisClient(addr string) *redis.Client {
	return redis.NewClient(&redis.Options{Addr: addr})
}
