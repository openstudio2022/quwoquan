package redis

import (
	"context"
	"time"

	"quwoquan_service/runtime/recommendation"
)

// recAdapter bridges redis.Client → recommendation.RedisClient (+ RedisPipeliner).
type recAdapter struct {
	client Client
}

// NewRecAdapter wraps a redis.Client as a recommendation.RedisClient.
// Also implements recommendation.RedisPipeliner for single-RTT pipeline reads.
func NewRecAdapter(client Client) recommendation.RedisClient {
	return &recAdapter{client: client}
}

func (a *recAdapter) Get(ctx context.Context, key string) (string, error) {
	return a.client.Get(ctx, key)
}

func (a *recAdapter) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	return a.client.Set(ctx, key, value, ttl)
}

func (a *recAdapter) Del(ctx context.Context, keys ...string) error {
	return a.client.Del(ctx, keys...)
}

func (a *recAdapter) SAdd(ctx context.Context, key string, members ...string) error {
	return a.client.SAdd(ctx, key, members...)
}

func (a *recAdapter) SMembers(ctx context.Context, key string) ([]string, error) {
	return a.client.SMembers(ctx, key)
}

func (a *recAdapter) SIsMember(ctx context.Context, key, member string) (bool, error) {
	return a.client.SIsMember(ctx, key, member)
}

func (a *recAdapter) HIncrByFloat(ctx context.Context, key, field string, incr float64) error {
	return a.client.HIncrByFloat(ctx, key, field, incr)
}

func (a *recAdapter) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return a.client.HGetAll(ctx, key)
}

func (a *recAdapter) Expire(ctx context.Context, key string, ttl time.Duration) error {
	return a.client.Expire(ctx, key, ttl)
}

// PipelineRead implements recommendation.RedisPipeliner for single-RTT reads.
func (a *recAdapter) PipelineRead(ctx context.Context, ops []recommendation.PipelineOp) error {
	pipe := a.client.Pipeline(ctx)

	hResults := make([]*MapResult, 0, len(ops))
	sResults := make([]*SliceResult, 0, len(ops))
	hIndices := make([]int, 0, len(ops))
	sIndices := make([]int, 0, len(ops))

	for i, op := range ops {
		switch op.Type {
		case recommendation.PipelineHGetAll:
			r := pipe.HGetAll(ctx, op.Key)
			hResults = append(hResults, r)
			hIndices = append(hIndices, i)
		case recommendation.PipelineSMembers:
			r := pipe.SMembers(ctx, op.Key)
			sResults = append(sResults, r)
			sIndices = append(sIndices, i)
		}
	}

	if err := pipe.Exec(ctx); err != nil {
		return err
	}

	for j, idx := range hIndices {
		val, err := hResults[j].Result()
		if err != nil {
			return err
		}
		ops[idx].Hash = val
	}

	for j, idx := range sIndices {
		val, err := sResults[j].Result()
		if err != nil {
			return err
		}
		ops[idx].Set = val
	}

	return nil
}
