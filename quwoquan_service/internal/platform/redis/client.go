package redis

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	goredis "github.com/redis/go-redis/v9"

	rtredis "quwoquan_service/runtime/redis"
)

func MustNewRouter(cfg rtredis.RouterConfig) *rtredis.Router {
	router, err := NewRouter(cfg)
	if err != nil {
		panic(fmt.Sprintf("redis.MustNewRouter: %v", err))
	}
	return router
}

func NewRouter(cfg rtredis.RouterConfig) (*rtredis.Router, error) {
	return rtredis.NewRouterWithFactory(cfg, newSceneClient)
}

func newSceneClient(cfg rtredis.SceneConfig) (rtredis.Client, error) {
	switch cfg.Mode {
	case "cluster":
		return newClusterClient(cfg)
	case "standalone":
		return newStandaloneClient(cfg)
	case "memory", "":
		return rtredis.NewMemoryClient(), nil
	default:
		return nil, fmt.Errorf("redis: unsupported mode %q", cfg.Mode)
	}
}

type client struct {
	raw goredis.UniversalClient
}

func newStandaloneClient(cfg rtredis.SceneConfig) (rtredis.Client, error) {
	if cfg.Addr == "" {
		return rtredis.NewMemoryClient(), nil
	}
	opts := &goredis.Options{
		Addr:     cfg.Addr,
		Password: cfg.Password,
		DB:       cfg.DB,
	}
	applyStandaloneOptions(opts, cfg)
	return &client{raw: goredis.NewClient(opts)}, nil
}

func newClusterClient(cfg rtredis.SceneConfig) (rtredis.Client, error) {
	if len(cfg.Addrs) == 0 {
		return rtredis.NewMemoryClient(), nil
	}
	opts := &goredis.ClusterOptions{
		Addrs:    cfg.Addrs,
		Password: cfg.Password,
	}
	applyClusterOptions(opts, cfg)
	return &client{raw: goredis.NewClusterClient(opts)}, nil
}

func applyStandaloneOptions(opts *goredis.Options, cfg rtredis.SceneConfig) {
	if cfg.PoolSize > 0 {
		opts.PoolSize = cfg.PoolSize
	}
	if cfg.MinIdleConns > 0 {
		opts.MinIdleConns = cfg.MinIdleConns
	}
	if cfg.DialTimeoutMs > 0 {
		opts.DialTimeout = time.Duration(cfg.DialTimeoutMs) * time.Millisecond
	}
	if cfg.ReadTimeoutMs > 0 {
		opts.ReadTimeout = time.Duration(cfg.ReadTimeoutMs) * time.Millisecond
	}
	if cfg.WriteTimeoutMs > 0 {
		opts.WriteTimeout = time.Duration(cfg.WriteTimeoutMs) * time.Millisecond
	}
	if cfg.TLS {
		opts.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
	}
}

func applyClusterOptions(opts *goredis.ClusterOptions, cfg rtredis.SceneConfig) {
	if cfg.PoolSize > 0 {
		opts.PoolSize = cfg.PoolSize
	}
	if cfg.MinIdleConns > 0 {
		opts.MinIdleConns = cfg.MinIdleConns
	}
	if cfg.DialTimeoutMs > 0 {
		opts.DialTimeout = time.Duration(cfg.DialTimeoutMs) * time.Millisecond
	}
	if cfg.ReadTimeoutMs > 0 {
		opts.ReadTimeout = time.Duration(cfg.ReadTimeoutMs) * time.Millisecond
	}
	if cfg.WriteTimeoutMs > 0 {
		opts.WriteTimeout = time.Duration(cfg.WriteTimeoutMs) * time.Millisecond
	}
	if cfg.TLS {
		opts.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
	}
}

func (c *client) Get(ctx context.Context, key string) (string, error) {
	value, err := c.raw.Get(ctx, key).Result()
	return value, normalizeNotFound(err)
}

func (c *client) GetBytes(ctx context.Context, key string) ([]byte, error) {
	value, err := c.raw.Get(ctx, key).Bytes()
	return value, normalizeNotFound(err)
}

func (c *client) GetDel(ctx context.Context, key string) (string, error) {
	value, err := c.raw.GetDel(ctx, key).Result()
	return value, normalizeNotFound(err)
}

func (c *client) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	return c.raw.Set(ctx, key, value, ttl).Err()
}

func (c *client) SetBytes(
	ctx context.Context,
	key string,
	value []byte,
	ttl time.Duration,
) error {
	return c.raw.Set(ctx, key, value, ttl).Err()
}

func (c *client) SetNX(
	ctx context.Context,
	key, value string,
	ttl time.Duration,
) (bool, error) {
	return c.raw.SetNX(ctx, key, value, ttl).Result()
}

func (c *client) Del(ctx context.Context, keys ...string) error {
	return c.raw.Del(ctx, keys...).Err()
}

func (c *client) Incr(ctx context.Context, key string) (int64, error) {
	return c.raw.Incr(ctx, key).Result()
}

func (c *client) Expire(ctx context.Context, key string, ttl time.Duration) error {
	return c.raw.Expire(ctx, key, ttl).Err()
}

func (c *client) HSet(ctx context.Context, key, field, value string) error {
	return c.raw.HSet(ctx, key, field, value).Err()
}

func (c *client) HGet(ctx context.Context, key, field string) (string, error) {
	value, err := c.raw.HGet(ctx, key, field).Result()
	return value, normalizeNotFound(err)
}

func (c *client) HDel(ctx context.Context, key string, fields ...string) error {
	return c.raw.HDel(ctx, key, fields...).Err()
}

func (c *client) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return c.raw.HGetAll(ctx, key).Result()
}

func (c *client) HIncrByFloat(
	ctx context.Context,
	key, field string,
	increment float64,
) error {
	return c.raw.HIncrByFloat(ctx, key, field, increment).Err()
}

func (c *client) SAdd(ctx context.Context, key string, members ...string) error {
	return c.raw.SAdd(ctx, key, stringArguments(members)...).Err()
}

func (c *client) SRem(ctx context.Context, key string, members ...string) error {
	return c.raw.SRem(ctx, key, stringArguments(members)...).Err()
}

func (c *client) SMembers(ctx context.Context, key string) ([]string, error) {
	return c.raw.SMembers(ctx, key).Result()
}

func (c *client) SIsMember(ctx context.Context, key, member string) (bool, error) {
	return c.raw.SIsMember(ctx, key, member).Result()
}

func (c *client) ZAdd(ctx context.Context, key string, score float64, member string) error {
	return c.raw.ZAdd(ctx, key, goredis.Z{Score: score, Member: member}).Err()
}

func (c *client) ZRangeByScore(
	ctx context.Context,
	key string,
	min, max float64,
	limit int,
) ([]string, error) {
	query := &goredis.ZRangeBy{
		Min: strconv.FormatFloat(min, 'f', -1, 64),
		Max: strconv.FormatFloat(max, 'f', -1, 64),
	}
	if limit > 0 {
		query.Count = int64(limit)
	}
	return c.raw.ZRangeByScore(ctx, key, query).Result()
}

func (c *client) ZRem(ctx context.Context, key string, members ...string) error {
	return c.raw.ZRem(ctx, key, stringArguments(members)...).Err()
}

func (c *client) ZCard(ctx context.Context, key string) (int64, error) {
	return c.raw.ZCard(ctx, key).Result()
}

func (c *client) Publish(ctx context.Context, channel, message string) error {
	return c.raw.Publish(ctx, channel, message).Err()
}

func (c *client) Subscribe(
	ctx context.Context,
	channels ...string,
) (rtredis.Subscription, error) {
	pubsub := c.raw.Subscribe(ctx, channels...)
	if _, err := pubsub.Receive(ctx); err != nil {
		_ = pubsub.Close()
		return nil, err
	}
	return &subscription{raw: pubsub}, nil
}

type subscription struct {
	raw     *goredis.PubSub
	once    sync.Once
	channel chan rtredis.Message
}

func (s *subscription) Channel() <-chan rtredis.Message {
	s.once.Do(func() {
		s.channel = make(chan rtredis.Message, 64)
		go func() {
			defer close(s.channel)
			for message := range s.raw.Channel() {
				s.channel <- rtredis.Message{Channel: message.Channel, Payload: message.Payload}
			}
		}()
	})
	return s.channel
}

func (s *subscription) Close() error {
	return s.raw.Close()
}

func (c *client) XGroupCreateMkStream(
	ctx context.Context,
	stream, group, start string,
) error {
	err := c.raw.XGroupCreateMkStream(ctx, stream, group, start).Err()
	if err != nil && strings.Contains(err.Error(), "BUSYGROUP") {
		return nil
	}
	return err
}

func (c *client) XAdd(
	ctx context.Context,
	stream string,
	values map[string]string,
) (string, error) {
	arguments := make(map[string]interface{}, len(values))
	for key, value := range values {
		arguments[key] = value
	}
	return c.raw.XAdd(
		ctx,
		&goredis.XAddArgs{Stream: stream, Values: arguments},
	).Result()
}

func (c *client) XReadGroup(
	ctx context.Context,
	group, consumer string,
	streams map[string]string,
	count int64,
	block time.Duration,
) ([]rtredis.StreamMessage, error) {
	streamArguments := orderedStreamArguments(streams)
	block = normalizeXReadGroupBlock(block)
	result, err := c.raw.XReadGroup(ctx, &goredis.XReadGroupArgs{
		Group: group, Consumer: consumer, Streams: streamArguments, Count: count, Block: block,
	}).Result()
	if errors.Is(err, goredis.Nil) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	output := make([]rtredis.StreamMessage, 0)
	for _, stream := range result {
		for _, message := range stream.Messages {
			output = append(output, rtredis.StreamMessage{
				Stream: stream.Stream,
				ID:     message.ID,
				Values: stringValueMap(message.Values),
			})
		}
	}
	return output, nil
}

func (c *client) XAck(
	ctx context.Context,
	stream, group string,
	ids ...string,
) error {
	if len(ids) == 0 {
		return nil
	}
	return c.raw.XAck(ctx, stream, group, ids...).Err()
}

func (c *client) XAutoClaim(
	ctx context.Context,
	stream, group, consumer string,
	minIdle time.Duration,
	start string,
	count int64,
) ([]rtredis.StreamMessage, string, error) {
	messages, next, err := c.raw.XAutoClaim(ctx, &goredis.XAutoClaimArgs{
		Stream: stream, Group: group, Consumer: consumer, MinIdle: minIdle, Start: start, Count: count,
	}).Result()
	if errors.Is(err, goredis.Nil) {
		return nil, next, nil
	}
	if err != nil {
		return nil, next, err
	}
	output := make([]rtredis.StreamMessage, 0, len(messages))
	for _, message := range messages {
		output = append(output, rtredis.StreamMessage{
			Stream: stream,
			ID:     message.ID,
			Values: stringValueMap(message.Values),
		})
	}
	return output, next, nil
}

func (c *client) Pipeline(context.Context) rtredis.Pipeliner {
	return &pipeline{raw: c.raw.Pipeline()}
}

func (c *client) Close() error {
	return c.raw.Close()
}

func (c *client) Ping(ctx context.Context) error {
	return c.raw.Ping(ctx).Err()
}

type pipeline struct {
	raw          goredis.Pipeliner
	getCommands  []*goredis.StringCmd
	hashCommands []*goredis.MapStringStringCmd
	setCommands  []*goredis.StringSliceCmd
	boolCommands []*goredis.BoolCmd
	getResults   []*rtredis.StringResult
	hashResults  []*rtredis.MapResult
	setResults   []*rtredis.SliceResult
	boolResults  []*rtredis.BoolResult
}

func (p *pipeline) Get(ctx context.Context, key string) *rtredis.StringResult {
	result := rtredis.NewStringResult("", nil)
	p.getCommands = append(p.getCommands, p.raw.Get(ctx, key))
	p.getResults = append(p.getResults, result)
	return result
}

func (p *pipeline) Set(
	ctx context.Context,
	key, value string,
	ttl time.Duration,
) {
	p.raw.Set(ctx, key, value, ttl)
}

func (p *pipeline) HGetAll(ctx context.Context, key string) *rtredis.MapResult {
	result := rtredis.NewMapResult(nil, nil)
	p.hashCommands = append(p.hashCommands, p.raw.HGetAll(ctx, key))
	p.hashResults = append(p.hashResults, result)
	return result
}

func (p *pipeline) SMembers(ctx context.Context, key string) *rtredis.SliceResult {
	result := rtredis.NewSliceResult(nil, nil)
	p.setCommands = append(p.setCommands, p.raw.SMembers(ctx, key))
	p.setResults = append(p.setResults, result)
	return result
}

func (p *pipeline) SIsMember(
	ctx context.Context,
	key string,
	member string,
) *rtredis.BoolResult {
	result := rtredis.NewBoolResult(false, nil)
	p.boolCommands = append(p.boolCommands, p.raw.SIsMember(ctx, key, member))
	p.boolResults = append(p.boolResults, result)
	return result
}

func (p *pipeline) Exec(ctx context.Context) error {
	_, err := p.raw.Exec(ctx)
	if errors.Is(err, goredis.Nil) {
		err = nil
	}
	for index, command := range p.getCommands {
		value, resultErr := command.Result()
		p.getResults[index].SetResult(value, normalizeNotFound(resultErr))
	}
	for index, command := range p.hashCommands {
		value, resultErr := command.Result()
		p.hashResults[index].SetResult(value, resultErr)
	}
	for index, command := range p.setCommands {
		value, resultErr := command.Result()
		p.setResults[index].SetResult(value, resultErr)
	}
	for index, command := range p.boolCommands {
		value, resultErr := command.Result()
		p.boolResults[index].SetResult(value, resultErr)
	}
	return err
}

func normalizeNotFound(err error) error {
	if errors.Is(err, goredis.Nil) {
		return rtredis.ErrKeyNotFound
	}
	return err
}

func normalizeXReadGroupBlock(block time.Duration) time.Duration {
	if block <= 0 {
		return -1
	}
	return block
}

func stringArguments(values []string) []interface{} {
	output := make([]interface{}, len(values))
	for index, value := range values {
		output[index] = value
	}
	return output
}

func orderedStreamArguments(streams map[string]string) []string {
	names := make([]string, 0, len(streams))
	for name := range streams {
		names = append(names, name)
	}
	sort.Strings(names)
	output := append([]string(nil), names...)
	for _, name := range names {
		output = append(output, streams[name])
	}
	return output
}

func stringValueMap(values map[string]interface{}) map[string]string {
	output := make(map[string]string, len(values))
	for key, value := range values {
		output[key] = fmt.Sprint(value)
	}
	return output
}
