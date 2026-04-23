// Package redis provides a unified Redis client abstraction with scene-based
// routing, transparent standalone/cluster/memory mode switching, and adapter
// bridges for legacy interfaces (repository.CacheAdapter, recommendation.RedisClient).
//
// Key design: upper layers access Redis through Router.Scene(name) or
// Router.ForKey(key) — the topology (standalone vs cluster, which instance)
// is fully transparent.
package redis

import (
	"context"
	"time"
)

// Client is the unified superset interface covering K/V, Hash, Set, Sorted-Set,
// Pub/Sub, and Pipeline operations. Every scene pool returns a Client.
type Client interface {
	// ── String ──────────────────────────────────────────────
	Get(ctx context.Context, key string) (string, error)
	GetBytes(ctx context.Context, key string) ([]byte, error)
	Set(ctx context.Context, key string, value string, ttl time.Duration) error
	SetBytes(ctx context.Context, key string, value []byte, ttl time.Duration) error
	SetNX(ctx context.Context, key string, value string, ttl time.Duration) (bool, error)
	Del(ctx context.Context, keys ...string) error
	Incr(ctx context.Context, key string) (int64, error)
	Expire(ctx context.Context, key string, ttl time.Duration) error

	// ── Hash ────────────────────────────────────────────────
	HSet(ctx context.Context, key string, field string, value string) error
	HGet(ctx context.Context, key, field string) (string, error)
	HDel(ctx context.Context, key string, fields ...string) error
	HGetAll(ctx context.Context, key string) (map[string]string, error)
	HIncrByFloat(ctx context.Context, key, field string, incr float64) error

	// ── Set ─────────────────────────────────────────────────
	SAdd(ctx context.Context, key string, members ...string) error
	SMembers(ctx context.Context, key string) ([]string, error)
	SIsMember(ctx context.Context, key string, member string) (bool, error)

	// ── Sorted Set ──────────────────────────────────────────
	ZAdd(ctx context.Context, key string, score float64, member string) error
	ZRangeByScore(ctx context.Context, key string, min, max float64, limit int) ([]string, error)
	ZRem(ctx context.Context, key string, members ...string) error
	ZCard(ctx context.Context, key string) (int64, error)

	// ── Pub/Sub ─────────────────────────────────────────────
	Publish(ctx context.Context, channel string, message string) error
	Subscribe(ctx context.Context, channels ...string) (Subscription, error)

	// ── Pipeline ────────────────────────────────────────────
	Pipeline(ctx context.Context) Pipeliner

	// ── Lifecycle ───────────────────────────────────────────
	Close() error
	Ping(ctx context.Context) error
}

// Subscription represents a Pub/Sub subscription.
type Subscription interface {
	Channel() <-chan Message
	Close() error
}

// Message is a Pub/Sub message.
type Message struct {
	Channel string
	Payload string
}

// Pipeliner batches multiple commands into a single round trip.
type Pipeliner interface {
	Get(ctx context.Context, key string) *StringResult
	Set(ctx context.Context, key string, value string, ttl time.Duration)
	HGetAll(ctx context.Context, key string) *MapResult
	SMembers(ctx context.Context, key string) *SliceResult
	Exec(ctx context.Context) error
}

// StringResult holds a deferred string result from a pipeline.
type StringResult struct {
	val string
	err error
}

func NewStringResult(val string, err error) *StringResult { return &StringResult{val: val, err: err} }
func (r *StringResult) Result() (string, error)           { return r.val, r.err }

// MapResult holds a deferred map result from a pipeline.
type MapResult struct {
	val map[string]string
	err error
}

func NewMapResult(val map[string]string, err error) *MapResult {
	return &MapResult{val: val, err: err}
}
func (r *MapResult) Result() (map[string]string, error) { return r.val, r.err }

// SliceResult holds a deferred slice result from a pipeline.
type SliceResult struct {
	val []string
	err error
}

func NewSliceResult(val []string, err error) *SliceResult { return &SliceResult{val: val, err: err} }
func (r *SliceResult) Result() ([]string, error)          { return r.val, r.err }

// ErrKeyNotFound is returned when a key does not exist.
// Callers should check errors.Is(err, ErrKeyNotFound).
var ErrKeyNotFound = errKeyNotFound{}

type errKeyNotFound struct{}

func (errKeyNotFound) Error() string { return "redis: key not found" }
