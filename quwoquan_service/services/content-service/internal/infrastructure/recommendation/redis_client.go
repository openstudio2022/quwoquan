package recommendation

import (
	"context"
	"runtime"
	"strconv"
	"time"

	redis "github.com/redis/go-redis/v9"
)

type RedisClientAdapter struct {
	client *redis.Client
}

// RedisPoolConfig tunes the connection pool for high-concurrency recommendation workloads.
type RedisPoolConfig struct {
	PoolSize     int
	MinIdleConns int
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	DialTimeout  time.Duration
}

// DefaultRedisPoolConfig returns pool settings tuned for recommendation hot path.
// Target: sustain 5000+ concurrent feed requests per process.
func DefaultRedisPoolConfig() RedisPoolConfig {
	cpus := runtime.GOMAXPROCS(0)
	return RedisPoolConfig{
		PoolSize:     cpus * 20,
		MinIdleConns: cpus * 5,
		ReadTimeout:  100 * time.Millisecond,
		WriteTimeout: 100 * time.Millisecond,
		DialTimeout:  500 * time.Millisecond,
	}
}

func NewRedisClientAdapter(addr string, password string, db int) *RedisClientAdapter {
	return NewRedisClientAdapterWithPool(addr, password, db, DefaultRedisPoolConfig())
}

func NewRedisClientAdapterWithPool(addr string, password string, db int, pool RedisPoolConfig) *RedisClientAdapter {
	c := redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     password,
		DB:           db,
		PoolSize:     pool.PoolSize,
		MinIdleConns: pool.MinIdleConns,
		ReadTimeout:  pool.ReadTimeout,
		WriteTimeout: pool.WriteTimeout,
		DialTimeout:  pool.DialTimeout,
	})
	return &RedisClientAdapter{client: c}
}

func (r *RedisClientAdapter) Get(ctx context.Context, key string) (string, error) {
	return r.client.Get(ctx, key).Result()
}

func (r *RedisClientAdapter) Set(ctx context.Context, key string, value string, ttl time.Duration) error {
	return r.client.Set(ctx, key, value, ttl).Err()
}

func (r *RedisClientAdapter) Del(ctx context.Context, keys ...string) error {
	return r.client.Del(ctx, keys...).Err()
}

func (r *RedisClientAdapter) SAdd(ctx context.Context, key string, members ...string) error {
	args := make([]any, 0, len(members))
	for _, m := range members {
		args = append(args, m)
	}
	return r.client.SAdd(ctx, key, args...).Err()
}

func (r *RedisClientAdapter) SMembers(ctx context.Context, key string) ([]string, error) {
	return r.client.SMembers(ctx, key).Result()
}

func (r *RedisClientAdapter) SIsMember(ctx context.Context, key string, member string) (bool, error) {
	return r.client.SIsMember(ctx, key, member).Result()
}

func (r *RedisClientAdapter) HIncrByFloat(ctx context.Context, key, field string, incr float64) error {
	return r.client.HIncrByFloat(ctx, key, field, incr).Err()
}

func (r *RedisClientAdapter) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return r.client.HGetAll(ctx, key).Result()
}

func (r *RedisClientAdapter) Expire(ctx context.Context, key string, ttl time.Duration) error {
	return r.client.Expire(ctx, key, ttl).Err()
}

func ParseRedisDB(raw string) int {
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 0
	}
	return n
}
