package recommendation

import (
	"context"
	"runtime"
	"strconv"
	"time"

	redis "github.com/redis/go-redis/v9"

	rtrec "quwoquan_service/runtime/recommendation"
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

// PipelineRead implements recommendation.RedisPipeliner — sends all ops in
// a single Redis pipeline RTT. Used by HotPath.GetSessionState to replace
// 3 parallel goroutines with 1 pipeline round-trip.
func (r *RedisClientAdapter) PipelineRead(ctx context.Context, ops []rtrec.PipelineOp) error {
	pipe := r.client.Pipeline()

	type pendingHash struct {
		idx int
		cmd *redis.MapStringStringCmd
	}
	type pendingSet struct {
		idx int
		cmd *redis.StringSliceCmd
	}

	hashes := make([]pendingHash, 0, len(ops))
	sets := make([]pendingSet, 0, len(ops))

	for i, op := range ops {
		switch op.Type {
		case rtrec.PipelineHGetAll:
			cmd := pipe.HGetAll(ctx, op.Key)
			hashes = append(hashes, pendingHash{idx: i, cmd: cmd})
		case rtrec.PipelineSMembers:
			cmd := pipe.SMembers(ctx, op.Key)
			sets = append(sets, pendingSet{idx: i, cmd: cmd})
		}
	}

	if _, err := pipe.Exec(ctx); err != nil && err != redis.Nil {
		return err
	}

	for _, h := range hashes {
		val, err := h.cmd.Result()
		if err != nil && err != redis.Nil {
			return err
		}
		ops[h.idx].Hash = val
	}
	for _, s := range sets {
		val, err := s.cmd.Result()
		if err != nil && err != redis.Nil {
			return err
		}
		ops[s.idx].Set = val
	}

	return nil
}

func ParseRedisDB(raw string) int {
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 0
	}
	return n
}
