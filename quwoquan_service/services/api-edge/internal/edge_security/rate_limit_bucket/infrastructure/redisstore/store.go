package redisstore

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"net/url"
	"strconv"
	"strings"
	"time"

	redis "github.com/redis/go-redis/v9"

	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
)

var consumeScript = redis.NewScript(`
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
if not limit or limit <= 0 or not window_ms or window_ms <= 0 then
  return redis.error_reply('limit and window_ms must be positive')
end
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('PEXPIRE', KEYS[1], window_ms)
end
local ttl_ms = redis.call('PTTL', KEYS[1])
if ttl_ms <= 0 then
  redis.call('PEXPIRE', KEYS[1], window_ms)
  ttl_ms = window_ms
end
if count > limit then
  count = limit + 1
  redis.call('SET', KEYS[1], count, 'PX', ttl_ms)
end
local allowed = 0
if count <= limit then
  allowed = 1
end
local remaining = limit - count
if remaining < 0 then
  remaining = 0
end
return {allowed, remaining, ttl_ms}
`)

type Config struct {
	Mode         string
	Addr         string
	Addrs        []string
	Password     string
	TLS          bool
	PoolSize     int
	DialTimeout  time.Duration
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
}

type Store struct {
	client redis.UniversalClient
}

var _ application.AtomicQuotaStore = (*Store)(nil)

func New(config Config) (*Store, error) {
	client, err := NewClient(config)
	if err != nil {
		return nil, err
	}
	return &Store{client: client}, nil
}

func NewWithClient(client redis.UniversalClient) (*Store, error) {
	if client == nil {
		return nil, errors.New("redis admission client is required")
	}
	return &Store{client: client}, nil
}

func NewClient(config Config) (redis.UniversalClient, error) {
	config.Mode = strings.TrimSpace(config.Mode)
	if config.Mode != "standalone" && config.Mode != "cluster" {
		return nil, fmt.Errorf("api-edge Redis mode must be standalone or cluster, got %q", config.Mode)
	}
	if config.DialTimeout <= 0 || config.ReadTimeout <= 0 || config.WriteTimeout <= 0 {
		return nil, errors.New("api-edge Redis timeouts must be positive")
	}
	if config.PoolSize <= 0 {
		return nil, errors.New("api-edge Redis pool size must be positive")
	}
	if config.Mode == "cluster" {
		if len(config.Addrs) < 3 {
			return nil, errors.New("api-edge Redis cluster requires at least three addresses")
		}
		options := &redis.ClusterOptions{
			Addrs:        normalizedAddresses(config.Addrs),
			Password:     config.Password,
			PoolSize:     config.PoolSize,
			DialTimeout:  config.DialTimeout,
			ReadTimeout:  config.ReadTimeout,
			WriteTimeout: config.WriteTimeout,
		}
		if config.TLS {
			options.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
		}
		return redis.NewClusterClient(options), nil
	}
	network, address, err := standaloneAddress(config.Addr)
	if err != nil {
		return nil, err
	}
	options := &redis.Options{
		Network:      network,
		Addr:         address,
		Password:     config.Password,
		PoolSize:     config.PoolSize,
		DialTimeout:  config.DialTimeout,
		ReadTimeout:  config.ReadTimeout,
		WriteTimeout: config.WriteTimeout,
	}
	if config.TLS {
		if network != "tcp" {
			return nil, errors.New("api-edge Redis TLS requires TCP")
		}
		options.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
	}
	return redis.NewClient(options), nil
}

func (store *Store) Consume(
	ctx context.Context,
	key string,
	limit int64,
	window time.Duration,
) (application.QuotaResult, error) {
	if store == nil || store.client == nil {
		return application.QuotaResult{}, errors.New("redis admission store is not configured")
	}
	result, err := consumeScript.Run(
		ctx,
		store.client,
		[]string{key},
		strconv.FormatInt(limit, 10),
		strconv.FormatInt(window.Milliseconds(), 10),
	).Slice()
	if err != nil {
		return application.QuotaResult{}, fmt.Errorf("consume Redis admission quota: %w", err)
	}
	if len(result) != 3 {
		return application.QuotaResult{}, fmt.Errorf("Redis admission result length=%d, want 3", len(result))
	}
	allowed, err := scriptInt64(result[0])
	if err != nil || (allowed != 0 && allowed != 1) {
		return application.QuotaResult{}, fmt.Errorf("Redis admission allowed value %v: %w", result[0], err)
	}
	remaining, err := scriptInt64(result[1])
	if err != nil || remaining < 0 {
		return application.QuotaResult{}, fmt.Errorf("Redis admission remaining value %v: %w", result[1], err)
	}
	ttlMilliseconds, err := scriptInt64(result[2])
	if err != nil || ttlMilliseconds <= 0 || ttlMilliseconds > window.Milliseconds() {
		return application.QuotaResult{}, fmt.Errorf("Redis admission TTL value %v: %w", result[2], err)
	}
	return application.QuotaResult{
		Allowed:    allowed == 1,
		Remaining:  remaining,
		RetryAfter: time.Duration(ttlMilliseconds) * time.Millisecond,
	}, nil
}

func (store *Store) Ping(ctx context.Context) error {
	if store == nil || store.client == nil {
		return errors.New("redis admission store is not configured")
	}
	return store.client.Ping(ctx).Err()
}

func (store *Store) Close() error {
	if store == nil || store.client == nil {
		return nil
	}
	return store.client.Close()
}

func normalizedAddresses(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func standaloneAddress(raw string) (network string, address string, err error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", "", errors.New("api-edge Redis address is required")
	}
	if !strings.HasPrefix(raw, "unix://") {
		return "tcp", raw, nil
	}
	parsed, parseErr := url.Parse(raw)
	if parseErr != nil || parsed.Path == "" || parsed.Host != "" {
		return "", "", fmt.Errorf("invalid Redis unix address %q", raw)
	}
	return "unix", parsed.Path, nil
}

func scriptInt64(value any) (int64, error) {
	switch typed := value.(type) {
	case int64:
		return typed, nil
	case string:
		return strconv.ParseInt(typed, 10, 64)
	case []byte:
		return strconv.ParseInt(string(typed), 10, 64)
	default:
		return 0, fmt.Errorf("unsupported Redis integer type %T", value)
	}
}
