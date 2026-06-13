package cache

import rtredis "quwoquan_service/runtime/redis"

// NewMiniredisClient creates a redis.Client suitable for miniredis in tests.
func NewMiniredisClient(_ string) rtredis.Client {
	return rtredis.NewMemoryClient()
}
