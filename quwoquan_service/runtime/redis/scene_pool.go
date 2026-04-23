package redis

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"strconv"
	"time"

	goredis "github.com/redis/go-redis/v9"
)

// newSceneClient creates a Client for the given scene config.
func newSceneClient(cfg SceneConfig) (Client, error) {
	switch cfg.Mode {
	case "cluster":
		return newClusterClient(cfg)
	case "standalone":
		return newStandaloneClient(cfg)
	case "memory", "":
		return NewMemoryClient(), nil
	default:
		return nil, fmt.Errorf("redis: unsupported mode %q (use standalone/cluster/memory)", cfg.Mode)
	}
}

// ── go-redis wrapper ────────────────────────────────────

// goRedisClient wraps go-redis universal client to implement Client.
type goRedisClient struct {
	rdb goredis.UniversalClient
}

func newStandaloneClient(cfg SceneConfig) (Client, error) {
	if cfg.Addr == "" {
		return NewMemoryClient(), nil
	}
	opts := &goredis.Options{
		Addr:     cfg.Addr,
		Password: cfg.Password,
		DB:       cfg.DB,
	}
	if cfg.PoolSize > 0 {
		opts.PoolSize = cfg.PoolSize
	}
	if cfg.MinIdleConns > 0 {
		opts.MinIdleConns = cfg.MinIdleConns
	}
	if cfg.TLS {
		opts.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
	}
	return &goRedisClient{rdb: goredis.NewClient(opts)}, nil
}

func newClusterClient(cfg SceneConfig) (Client, error) {
	if len(cfg.Addrs) == 0 {
		return NewMemoryClient(), nil
	}
	opts := &goredis.ClusterOptions{
		Addrs:    cfg.Addrs,
		Password: cfg.Password,
	}
	if cfg.PoolSize > 0 {
		opts.PoolSize = cfg.PoolSize
	}
	if cfg.MinIdleConns > 0 {
		opts.MinIdleConns = cfg.MinIdleConns
	}
	if cfg.TLS {
		opts.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
	}
	return &goRedisClient{rdb: goredis.NewClusterClient(opts)}, nil
}

// ── String ──────────────────────────────────────────────

func (c *goRedisClient) Get(ctx context.Context, key string) (string, error) {
	val, err := c.rdb.Get(ctx, key).Result()
	if errors.Is(err, goredis.Nil) {
		return "", ErrKeyNotFound
	}
	return val, err
}

func (c *goRedisClient) GetBytes(ctx context.Context, key string) ([]byte, error) {
	val, err := c.rdb.Get(ctx, key).Bytes()
	if errors.Is(err, goredis.Nil) {
		return nil, ErrKeyNotFound
	}
	return val, err
}

func (c *goRedisClient) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	return c.rdb.Set(ctx, key, value, ttl).Err()
}

func (c *goRedisClient) SetBytes(ctx context.Context, key string, value []byte, ttl time.Duration) error {
	return c.rdb.Set(ctx, key, value, ttl).Err()
}

func (c *goRedisClient) SetNX(ctx context.Context, key, value string, ttl time.Duration) (bool, error) {
	return c.rdb.SetNX(ctx, key, value, ttl).Result()
}

func (c *goRedisClient) Del(ctx context.Context, keys ...string) error {
	return c.rdb.Del(ctx, keys...).Err()
}

func (c *goRedisClient) Incr(ctx context.Context, key string) (int64, error) {
	return c.rdb.Incr(ctx, key).Result()
}

func (c *goRedisClient) Expire(ctx context.Context, key string, ttl time.Duration) error {
	return c.rdb.Expire(ctx, key, ttl).Err()
}

// ── Hash ────────────────────────────────────────────────

func (c *goRedisClient) HSet(ctx context.Context, key, field, value string) error {
	return c.rdb.HSet(ctx, key, field, value).Err()
}

func (c *goRedisClient) HGet(ctx context.Context, key, field string) (string, error) {
	val, err := c.rdb.HGet(ctx, key, field).Result()
	if errors.Is(err, goredis.Nil) {
		return "", ErrKeyNotFound
	}
	return val, err
}

func (c *goRedisClient) HDel(ctx context.Context, key string, fields ...string) error {
	return c.rdb.HDel(ctx, key, fields...).Err()
}

func (c *goRedisClient) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return c.rdb.HGetAll(ctx, key).Result()
}

func (c *goRedisClient) HIncrByFloat(ctx context.Context, key, field string, incr float64) error {
	return c.rdb.HIncrByFloat(ctx, key, field, incr).Err()
}

// ── Set ─────────────────────────────────────────────────

func (c *goRedisClient) SAdd(ctx context.Context, key string, members ...string) error {
	args := make([]interface{}, len(members))
	for i, m := range members {
		args[i] = m
	}
	return c.rdb.SAdd(ctx, key, args...).Err()
}

func (c *goRedisClient) SMembers(ctx context.Context, key string) ([]string, error) {
	return c.rdb.SMembers(ctx, key).Result()
}

func (c *goRedisClient) SIsMember(ctx context.Context, key, member string) (bool, error) {
	return c.rdb.SIsMember(ctx, key, member).Result()
}

// ── Sorted Set ───────────────────────────────────────────

func (c *goRedisClient) ZAdd(ctx context.Context, key string, score float64, member string) error {
	return c.rdb.ZAdd(ctx, key, goredis.Z{Score: score, Member: member}).Err()
}

func (c *goRedisClient) ZRangeByScore(ctx context.Context, key string, min, max float64, limit int) ([]string, error) {
	opt := &goredis.ZRangeBy{
		Min: strconv.FormatFloat(min, 'f', -1, 64),
		Max: strconv.FormatFloat(max, 'f', -1, 64),
	}
	if limit > 0 {
		opt.Offset = 0
		opt.Count = int64(limit)
	}
	return c.rdb.ZRangeByScore(ctx, key, opt).Result()
}

func (c *goRedisClient) ZRem(ctx context.Context, key string, members ...string) error {
	args := make([]interface{}, len(members))
	for i, member := range members {
		args[i] = member
	}
	return c.rdb.ZRem(ctx, key, args...).Err()
}

func (c *goRedisClient) ZCard(ctx context.Context, key string) (int64, error) {
	return c.rdb.ZCard(ctx, key).Result()
}

// ── Pub/Sub ─────────────────────────────────────────────

func (c *goRedisClient) Publish(ctx context.Context, channel, message string) error {
	return c.rdb.Publish(ctx, channel, message).Err()
}

func (c *goRedisClient) Subscribe(ctx context.Context, channels ...string) (Subscription, error) {
	ps := c.rdb.Subscribe(ctx, channels...)
	return &goRedisSub{ps: ps}, nil
}

type goRedisSub struct {
	ps *goredis.PubSub
}

func (s *goRedisSub) Channel() <-chan Message {
	ch := make(chan Message, 64)
	go func() {
		defer close(ch)
		for msg := range s.ps.Channel() {
			ch <- Message{Channel: msg.Channel, Payload: msg.Payload}
		}
	}()
	return ch
}

func (s *goRedisSub) Close() error {
	return s.ps.Close()
}

// ── Pipeline ────────────────────────────────────────────

func (c *goRedisClient) Pipeline(_ context.Context) Pipeliner {
	return &goRedisPipeline{pipe: c.rdb.Pipeline()}
}

type goRedisPipeline struct {
	pipe goredis.Pipeliner
	gets []*goredis.StringCmd
	hgas []*goredis.MapStringStringCmd
	smem []*goredis.StringSliceCmd
	gres []*StringResult
	hres []*MapResult
	sres []*SliceResult
}

func (p *goRedisPipeline) Get(ctx context.Context, key string) *StringResult {
	cmd := p.pipe.Get(ctx, key)
	r := &StringResult{}
	p.gets = append(p.gets, cmd)
	p.gres = append(p.gres, r)
	return r
}

func (p *goRedisPipeline) Set(ctx context.Context, key, value string, ttl time.Duration) {
	p.pipe.Set(ctx, key, value, ttl)
}

func (p *goRedisPipeline) HGetAll(ctx context.Context, key string) *MapResult {
	cmd := p.pipe.HGetAll(ctx, key)
	r := &MapResult{}
	p.hgas = append(p.hgas, cmd)
	p.hres = append(p.hres, r)
	return r
}

func (p *goRedisPipeline) SMembers(ctx context.Context, key string) *SliceResult {
	cmd := p.pipe.SMembers(ctx, key)
	r := &SliceResult{}
	p.smem = append(p.smem, cmd)
	p.sres = append(p.sres, r)
	return r
}

func (p *goRedisPipeline) Exec(ctx context.Context) error {
	_, err := p.pipe.Exec(ctx)
	if errors.Is(err, goredis.Nil) {
		err = nil
	}
	for i, cmd := range p.gets {
		v, e := cmd.Result()
		if errors.Is(e, goredis.Nil) {
			e = ErrKeyNotFound
		}
		p.gres[i].val = v
		p.gres[i].err = e
	}
	for i, cmd := range p.hgas {
		v, e := cmd.Result()
		p.hres[i].val = v
		p.hres[i].err = e
	}
	for i, cmd := range p.smem {
		v, e := cmd.Result()
		p.sres[i].val = v
		p.sres[i].err = e
	}
	return err
}

// ── Lifecycle ───────────────────────────────────────────

func (c *goRedisClient) Close() error {
	return c.rdb.Close()
}

func (c *goRedisClient) Ping(ctx context.Context) error {
	return c.rdb.Ping(ctx).Err()
}
