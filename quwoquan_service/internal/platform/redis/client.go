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

	"quwoquan_service/runtime/boundedrecord"
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

	consumerGroupMu sync.Mutex
	// consumerGroups tracks the start position of every consumer group this
	// client ensured, so a NOGROUP after server-side state loss (failover,
	// FLUSHDB) can be healed by recreating the group once with the same
	// semantics instead of failing every subsequent read.
	consumerGroups map[string]string
	streamPolls    *streamPollGovernor
}

const (
	streamPollInitialDelay = 50 * time.Millisecond
	streamPollMaximumDelay = 500 * time.Millisecond
)

type streamPollState struct {
	emptyReads int
	nextPoll   time.Time
}

type streamPollGovernor struct {
	mu      sync.Mutex
	initial time.Duration
	maximum time.Duration
	states  map[string]streamPollState
}

func newStreamPollGovernor(initial, maximum time.Duration) *streamPollGovernor {
	if initial <= 0 || maximum < initial {
		panic("redis stream poll backoff bounds are invalid")
	}
	return &streamPollGovernor{
		initial: initial,
		maximum: maximum,
		states:  make(map[string]streamPollState),
	}
}

func (g *streamPollGovernor) delay(key string) time.Duration {
	g.mu.Lock()
	defer g.mu.Unlock()
	remaining := time.Until(g.states[key].nextPoll)
	if remaining < 0 {
		return 0
	}
	return remaining
}

func (g *streamPollGovernor) wait(ctx context.Context, key string) error {
	if g == nil {
		return nil
	}
	for {
		g.mu.Lock()
		state := g.states[key]
		remaining := time.Until(state.nextPoll)
		if remaining <= 0 {
			g.mu.Unlock()
			return nil
		}
		g.mu.Unlock()

		timer := time.NewTimer(remaining)
		select {
		case <-ctx.Done():
			if !timer.Stop() {
				<-timer.C
			}
			return ctx.Err()
		case <-timer.C:
		}
	}
}

func (g *streamPollGovernor) record(key string, messages int, err error) {
	if g == nil {
		return
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	if messages > 0 {
		delete(g.states, key)
		return
	}
	state := g.states[key]
	state.emptyReads++
	delay := g.initial
	for step := 1; step < state.emptyReads && delay < g.maximum; step++ {
		delay *= 2
		if delay > g.maximum {
			delay = g.maximum
		}
	}
	// Transient errors use the same bounded retry governance as a successful
	// empty read. They must not form a failure-command hot loop.
	_ = err
	state.nextPoll = time.Now().Add(delay)
	g.states[key] = state
}

func streamPollKey(stream, group string) string {
	return strings.TrimSpace(stream) + "\x00" + strings.TrimSpace(group)
}

func streamConsumerPollKey(stream, group, consumer string) string {
	return streamPollKey(stream, group) + "\x00" + strings.TrimSpace(consumer)
}

func streamPollKeyForRead(
	group, consumer string,
	streams map[string]string,
) string {
	streamNames := make([]string, 0, len(streams))
	for stream := range streams {
		streamNames = append(streamNames, strings.TrimSpace(stream))
	}
	sort.Strings(streamNames)
	return strings.Join(streamNames, "\x00") + "\x00" +
		strings.TrimSpace(group) + "\x00" + strings.TrimSpace(consumer)
}

type redisProtocolError interface {
	RedisError()
}

func isBusyGroupError(err error) bool {
	var protocolError redisProtocolError
	return errors.As(err, &protocolError) &&
		strings.HasPrefix(err.Error(), "BUSYGROUP ")
}

func isNoGroupError(err error) bool {
	var protocolError redisProtocolError
	return errors.As(err, &protocolError) &&
		strings.HasPrefix(err.Error(), "NOGROUP ")
}

func (c *client) invalidateConsumerGroups(
	group string,
	streams map[string]string,
) {
	c.consumerGroupMu.Lock()
	defer c.consumerGroupMu.Unlock()
	for stream := range streams {
		delete(c.consumerGroups, streamPollKey(stream, group))
	}
}

// recreateTrackedConsumerGroups rebuilds consumer groups this client already
// ensured after the server lost them. It returns true only when every
// requested stream had a tracked start position and was recreated, so the
// caller may retry the failed command exactly once; untracked groups keep
// surfacing the typed NOGROUP error.
func (c *client) recreateTrackedConsumerGroups(
	ctx context.Context,
	group string,
	streams map[string]string,
) bool {
	starts := make(map[string]string, len(streams))
	c.consumerGroupMu.Lock()
	for stream := range streams {
		start, tracked := c.consumerGroups[streamPollKey(stream, group)]
		if !tracked {
			c.consumerGroupMu.Unlock()
			return false
		}
		starts[stream] = start
	}
	c.consumerGroupMu.Unlock()
	for stream, start := range starts {
		err := c.raw.XGroupCreateMkStream(ctx, stream, group, start).Err()
		if err != nil && !isBusyGroupError(err) {
			return false
		}
	}
	return true
}

func (c *client) pollGovernor() *streamPollGovernor {
	c.consumerGroupMu.Lock()
	defer c.consumerGroupMu.Unlock()
	if c.streamPolls == nil {
		c.streamPolls = newStreamPollGovernor(
			streamPollInitialDelay,
			streamPollMaximumDelay,
		)
	}
	return c.streamPolls
}

var compareAndSwapHashFieldScript = goredis.NewScript(`
local current = redis.call('HGET', KEYS[1], ARGV[1])
local expects_value = ARGV[2] == '1'
if expects_value then
  if not current or current ~= ARGV[3] then
    return 0
  end
elseif current then
  return 0
end

if ARGV[4] == '1' then
  redis.call('HSET', KEYS[1], ARGV[1], ARGV[5])
  local ttl_ms = tonumber(ARGV[6])
  if ttl_ms and ttl_ms > 0 then
    redis.call('PEXPIRE', KEYS[1], ttl_ms)
  end
else
  redis.call('HDEL', KEYS[1], ARGV[1])
end
return 1
`)

var boundedImmutableRecordAtomicCreateScript = goredis.NewScript(`
local ttl_ms = tonumber(ARGV[2])
local owner_digest = ARGV[3]
local max_owner = tonumber(ARGV[4])
local max_shard_records = tonumber(ARGV[5])
local max_shard_bytes = tonumber(ARGV[6])
local payload_bytes = tonumber(ARGV[7])
if not ttl_ms or ttl_ms <= 0 or not max_owner or max_owner <= 0
  or not max_shard_records or max_shard_records <= 0
  or not max_shard_bytes or max_shard_bytes <= 0
  or not payload_bytes or payload_bytes <= 0
  or max_owner > max_shard_records then
  return redis.error_reply('bounded immutable record policy is invalid')
end

local server_time = redis.call('TIME')
local now_us = tonumber(server_time[1]) * 1000000 + tonumber(server_time[2])
local expires_at_us = now_us + ttl_ms * 1000

local declared = {[KEYS[1]] = true}
for position = 4, #KEYS do
  declared[KEYS[position]] = true
end

local indexed = redis.call('ZRANGE', KEYS[2], 0, max_shard_records)
if #indexed > max_shard_records then
  return {'', -4, 0, #indexed, 0}
end
for position = 1, #indexed do
  if not declared[indexed[position]] then
    return {'', -1, 0, #indexed, 0}
  end
end

for position = 1, #indexed do
  local candidate = indexed[position]
  local expiry = redis.call('ZSCORE', KEYS[2], candidate)
  local exists = redis.call('EXISTS', candidate)
  if not expiry or tonumber(expiry) <= now_us or exists == 0 then
    redis.call('ZREM', KEYS[2], candidate)
    redis.call('HDEL', KEYS[3], candidate)
    if expiry and tonumber(expiry) <= now_us then
      redis.call('DEL', candidate)
    end
  end
end

indexed = redis.call('ZRANGE', KEYS[2], 0, max_shard_records)
local live_records = 0
local live_bytes = 0
local owner_records = {}
for position = 1, #indexed do
  local candidate = indexed[position]
  local metadata = redis.call('HGET', KEYS[3], candidate)
  if not metadata then
    return {'', -4, 0, #indexed, live_bytes}
  end
  local candidate_owner, candidate_bytes_text =
    string.match(metadata, '^([0-9a-f]+):([0-9]+)$')
  local candidate_bytes = tonumber(candidate_bytes_text)
  if not candidate_owner or not candidate_bytes or candidate_bytes <= 0 then
    return {'', -4, 0, #indexed, live_bytes}
  end
  live_records = live_records + 1
  live_bytes = live_bytes + candidate_bytes
  if candidate_owner == owner_digest then
    owner_records[#owner_records + 1] = {
      key = candidate,
      bytes = candidate_bytes,
    }
  end
end

local existing = redis.call('GET', KEYS[1])
if existing then
  local metadata = redis.call('HGET', KEYS[3], KEYS[1])
  local indexed_expiry = redis.call('ZSCORE', KEYS[2], KEYS[1])
  if not metadata or not indexed_expiry then
    return {'', -4, 0, live_records, live_bytes}
  end
  local existing_owner, existing_bytes_text =
    string.match(metadata, '^([0-9a-f]+):([0-9]+)$')
  local existing_bytes = tonumber(existing_bytes_text)
  if existing_owner ~= owner_digest or existing_bytes ~= string.len(existing) then
    return {'', -4, 0, live_records, live_bytes}
  end
  return {existing, 0, 0, live_records, live_bytes}
end

local owner_eviction_count = #owner_records - max_owner + 1
if owner_eviction_count < 0 then
  owner_eviction_count = 0
end
local owner_eviction_bytes = 0
for position = 1, owner_eviction_count do
  owner_eviction_bytes = owner_eviction_bytes + owner_records[position].bytes
end

local projected_records = live_records - owner_eviction_count + 1
local projected_bytes = live_bytes - owner_eviction_bytes + payload_bytes
if projected_records > max_shard_records then
  return {'', -2, 0, live_records, live_bytes}
end
if projected_bytes > max_shard_bytes then
  return {'', -3, 0, live_records, live_bytes}
end

for position = 1, owner_eviction_count do
  local victim = owner_records[position].key
  redis.call('DEL', victim)
  redis.call('ZREM', KEYS[2], victim)
  redis.call('HDEL', KEYS[3], victim)
end

local persisted = redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ttl_ms)
if not persisted then
  return redis.error_reply('bounded immutable record atomic SET NX did not persist')
end
redis.call('ZADD', KEYS[2], expires_at_us, KEYS[1])
redis.call('HSET', KEYS[3], KEYS[1], owner_digest .. ':' .. payload_bytes)
local index_ttl_ms = redis.call('PTTL', KEYS[2])
if index_ttl_ms < ttl_ms then
  redis.call('PEXPIRE', KEYS[2], ttl_ms)
end
local metadata_ttl_ms = redis.call('PTTL', KEYS[3])
if metadata_ttl_ms < ttl_ms then
  redis.call('PEXPIRE', KEYS[3], ttl_ms)
end
return {'', 1, owner_eviction_count, projected_records, projected_bytes}
`)

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

func (c *client) CreateBoundedImmutableRecordAtomic(
	ctx context.Context,
	request boundedrecord.Request,
) (boundedrecord.Result, error) {
	if err := request.Validate(); err != nil {
		return boundedrecord.Result{}, err
	}
	recordTag, ok := redisClusterHashTag(request.RecordKey)
	if !ok {
		return boundedrecord.Result{}, errors.New(
			"bounded immutable record key must contain a Redis Cluster hash tag",
		)
	}
	for _, key := range []string{
		request.ShardIndexKey,
		request.ShardMetadataKey,
	} {
		tag, tagged := redisClusterHashTag(key)
		if !tagged || tag != recordTag {
			return boundedrecord.Result{}, errors.New(
				"bounded immutable record keys must share one Redis Cluster hash tag",
			)
		}
	}
	const maxAttempts = 16
	for attempt := 0; attempt < maxAttempts; attempt++ {
		// Read at most cap+1 members. Seeing cap+1 proves corruption/config
		// shrink without an unbounded scan. Every record Lua may inspect is then
		// an explicit EVAL key; a concurrent undeclared member returns retry.
		indexedKeys, err := c.raw.ZRange(
			ctx,
			request.ShardIndexKey,
			0,
			int64(request.Policy.MaximumLiveRecordsPerShard),
		).Result()
		if err != nil {
			return boundedrecord.Result{}, fmt.Errorf(
				"read bounded immutable record quota index: %w",
				err,
			)
		}
		if len(indexedKeys) > request.Policy.MaximumLiveRecordsPerShard {
			return boundedrecord.Result{}, fmt.Errorf(
				"%w: members=%d maximum=%d",
				boundedrecord.ErrRepairBound,
				len(indexedKeys),
				request.Policy.MaximumLiveRecordsPerShard,
			)
		}
		keys := make([]string, 0, len(indexedKeys)+3)
		keys = append(
			keys,
			request.RecordKey,
			request.ShardIndexKey,
			request.ShardMetadataKey,
		)
		for _, indexedKey := range indexedKeys {
			tag, tagged := redisClusterHashTag(indexedKey)
			if !tagged || tag != recordTag {
				return boundedrecord.Result{}, fmt.Errorf(
					"%w: indexed key escapes quota shard",
					boundedrecord.ErrRepairBound,
				)
			}
			if indexedKey != request.RecordKey {
				keys = append(keys, indexedKey)
			}
		}
		result, err := boundedImmutableRecordAtomicCreateScript.Run(
			ctx,
			c.raw,
			keys,
			request.Value,
			strconv.FormatInt(request.TTL.Milliseconds(), 10),
			request.OwnerDigest,
			strconv.Itoa(request.Policy.MaximumLiveRecordsPerOwner),
			strconv.Itoa(request.Policy.MaximumLiveRecordsPerShard),
			strconv.FormatInt(
				request.Policy.MaximumLiveBytesPerShard,
				10,
			),
			strconv.Itoa(len(request.Value)),
		).Slice()
		if err != nil {
			return boundedrecord.Result{}, err
		}
		if len(result) != 5 {
			return boundedrecord.Result{}, fmt.Errorf(
				"bounded immutable record atomic result length=%d, want 5",
				len(result),
			)
		}
		winner, err := redisScriptString(result[0])
		if err != nil {
			return boundedrecord.Result{}, fmt.Errorf(
				"bounded immutable record atomic winner: %w",
				err,
			)
		}
		status, err := redisScriptInt64(result[1])
		if err != nil {
			return boundedrecord.Result{}, fmt.Errorf(
				"bounded immutable record atomic status: %w",
				err,
			)
		}
		if status == -1 {
			continue
		}
		ownerEvicted, err := redisScriptInt64(result[2])
		if err != nil {
			return boundedrecord.Result{}, fmt.Errorf(
				"bounded immutable record atomic owner eviction count: %w",
				err,
			)
		}
		liveRecords, err := redisScriptInt64(result[3])
		if err != nil {
			return boundedrecord.Result{}, fmt.Errorf(
				"bounded immutable record atomic live records: %w",
				err,
			)
		}
		liveBytes, err := redisScriptInt64(result[4])
		if err != nil {
			return boundedrecord.Result{}, fmt.Errorf(
				"bounded immutable record atomic live bytes: %w",
				err,
			)
		}
		admission := boundedrecord.Result{
			Winner:       winner,
			Created:      status == 1,
			OwnerEvicted: ownerEvicted,
			UsageMeasured: status == 0 || status == 1 ||
				status == -2 || status == -3,
			LiveRecords: liveRecords,
			LiveBytes:   liveBytes,
		}
		switch status {
		case 0, 1:
			return admission, nil
		case -2:
			return admission, boundedrecord.ErrShardKeyQuota
		case -3:
			return admission, boundedrecord.ErrShardByteQuota
		case -4:
			return admission, boundedrecord.ErrRepairBound
		default:
			return boundedrecord.Result{}, fmt.Errorf(
				"bounded immutable record atomic status=%d",
				status,
			)
		}
	}
	return boundedrecord.Result{}, fmt.Errorf(
		"%w: exceeded %d retries",
		boundedrecord.ErrConcurrentIndexChange,
		maxAttempts,
	)
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

func (c *client) CompareAndSwapHashField(
	ctx context.Context,
	key string,
	field string,
	expected *string,
	replacement *string,
	ttl time.Duration,
) (bool, error) {
	expectsValue := "0"
	expectedValue := ""
	if expected != nil {
		expectsValue = "1"
		expectedValue = *expected
	}
	hasReplacement := "0"
	replacementValue := ""
	if replacement != nil {
		hasReplacement = "1"
		replacementValue = *replacement
	}
	result, err := compareAndSwapHashFieldScript.Run(
		ctx,
		c.raw,
		[]string{key},
		field,
		expectsValue,
		expectedValue,
		hasReplacement,
		replacementValue,
		ttl.Milliseconds(),
	).Int64()
	if err != nil {
		return false, err
	}
	return result == 1, nil
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
	key := streamPollKey(stream, group)
	c.consumerGroupMu.Lock()
	defer c.consumerGroupMu.Unlock()
	if _, initialized := c.consumerGroups[key]; initialized {
		return nil
	}
	err := c.raw.XGroupCreateMkStream(ctx, stream, group, start).Err()
	if err != nil && !isBusyGroupError(err) {
		return err
	}
	if c.consumerGroups == nil {
		c.consumerGroups = make(map[string]string)
	}
	c.consumerGroups[key] = start
	return nil
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

func (c *client) XRead(
	ctx context.Context,
	streams map[string]string,
	count int64,
	block time.Duration,
) ([]rtredis.StreamMessage, error) {
	streamArguments := orderedStreamArguments(streams)
	block = normalizeXReadGroupBlock(block)
	result, err := c.raw.XRead(ctx, &goredis.XReadArgs{
		Streams: streamArguments,
		Count:   count,
		Block:   block,
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

func (c *client) XReadGroup(
	ctx context.Context,
	group, consumer string,
	streams map[string]string,
	count int64,
	block time.Duration,
) ([]rtredis.StreamMessage, error) {
	pollKey := streamPollKeyForRead(group, consumer, streams)
	governor := c.pollGovernor()
	if err := governor.wait(ctx, pollKey); err != nil {
		return nil, err
	}
	streamArguments := orderedStreamArguments(streams)
	block = normalizeXReadGroupBlock(block)
	result, err := c.raw.XReadGroup(ctx, &goredis.XReadGroupArgs{
		Group: group, Consumer: consumer, Streams: streamArguments, Count: count, Block: block,
	}).Result()
	if isNoGroupError(err) && c.recreateTrackedConsumerGroups(ctx, group, streams) {
		result, err = c.raw.XReadGroup(ctx, &goredis.XReadGroupArgs{
			Group: group, Consumer: consumer, Streams: streamArguments, Count: count, Block: block,
		}).Result()
	}
	if errors.Is(err, goredis.Nil) {
		governor.record(pollKey, 0, nil)
		return nil, nil
	}
	if err != nil {
		if isNoGroupError(err) {
			c.invalidateConsumerGroups(group, streams)
		}
		governor.record(pollKey, 0, err)
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
	governor.record(pollKey, len(output), nil)
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
	pollKey := streamConsumerPollKey(stream, group, consumer)
	governor := c.pollGovernor()
	if err := governor.wait(ctx, pollKey); err != nil {
		return nil, start, err
	}
	messages, next, err := c.raw.XAutoClaim(ctx, &goredis.XAutoClaimArgs{
		Stream: stream, Group: group, Consumer: consumer, MinIdle: minIdle, Start: start, Count: count,
	}).Result()
	if isNoGroupError(err) && c.recreateTrackedConsumerGroups(
		ctx,
		group,
		map[string]string{stream: ">"},
	) {
		messages, next, err = c.raw.XAutoClaim(ctx, &goredis.XAutoClaimArgs{
			Stream: stream, Group: group, Consumer: consumer, MinIdle: minIdle, Start: start, Count: count,
		}).Result()
	}
	if errors.Is(err, goredis.Nil) {
		return nil, next, nil
	}
	if err != nil {
		if isNoGroupError(err) {
			c.invalidateConsumerGroups(
				group,
				map[string]string{stream: ">"},
			)
		}
		governor.record(pollKey, 0, err)
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
	governor.record(pollKey, len(output), nil)
	return output, next, nil
}

func (c *client) XPendingCount(
	ctx context.Context,
	stream string,
	group string,
) (int64, error) {
	pending, err := c.raw.XPending(ctx, stream, group).Result()
	if err != nil {
		return 0, err
	}
	return pending.Count, nil
}

func (c *client) XTrimOlderThan(
	ctx context.Context,
	stream string,
	maxAge time.Duration,
) error {
	if maxAge <= 0 {
		return fmt.Errorf("Redis stream max age must be positive")
	}
	serverTime, err := c.raw.Time(ctx).Result()
	if err != nil {
		return fmt.Errorf("read Redis server time: %w", err)
	}
	minID := fmt.Sprintf("%d-0", serverTime.Add(-maxAge).UnixMilli())
	return c.raw.XTrimMinID(ctx, stream, minID).Err()
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

func redisScriptString(value interface{}) (string, error) {
	switch typed := value.(type) {
	case string:
		return typed, nil
	case []byte:
		return string(typed), nil
	default:
		return "", fmt.Errorf("unexpected Redis script string type %T", value)
	}
}

func redisScriptInt64(value interface{}) (int64, error) {
	switch typed := value.(type) {
	case int64:
		return typed, nil
	case int:
		return int64(typed), nil
	case string:
		return strconv.ParseInt(typed, 10, 64)
	case []byte:
		return strconv.ParseInt(string(typed), 10, 64)
	default:
		return 0, fmt.Errorf("unexpected Redis script integer type %T", value)
	}
}

func redisClusterHashTag(key string) (string, bool) {
	start := strings.IndexByte(key, '{')
	if start < 0 {
		return "", false
	}
	remainder := key[start+1:]
	end := strings.IndexByte(remainder, '}')
	if end <= 0 {
		return "", false
	}
	return remainder[:end], true
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
