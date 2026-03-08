package redis

import (
	"context"
	"log"
	"sync/atomic"
	"time"
)

// MetricsCollector records per-scene Redis operation metrics.
// Default implementation uses atomic counters + periodic log output.
// Replace with Prometheus collectors when the project adopts it.
type MetricsCollector struct {
	scenes map[string]*sceneMetrics
}

type sceneMetrics struct {
	name    string
	ops     atomic.Int64
	errors  atomic.Int64
	totalNs atomic.Int64
}

// NewMetricsCollector creates a collector for the given scene names.
func NewMetricsCollector(sceneNames []string) *MetricsCollector {
	m := &MetricsCollector{
		scenes: make(map[string]*sceneMetrics, len(sceneNames)),
	}
	for _, n := range sceneNames {
		m.scenes[n] = &sceneMetrics{name: n}
	}
	return m
}

// Record records a single operation for a scene.
func (mc *MetricsCollector) Record(scene string, dur time.Duration, err error) {
	sm, ok := mc.scenes[scene]
	if !ok {
		return
	}
	sm.ops.Add(1)
	sm.totalNs.Add(int64(dur))
	if err != nil {
		sm.errors.Add(1)
	}
}

// Snapshot returns a point-in-time snapshot of all scene metrics.
func (mc *MetricsCollector) Snapshot() map[string]SceneSnapshot {
	result := make(map[string]SceneSnapshot, len(mc.scenes))
	for name, sm := range mc.scenes {
		ops := sm.ops.Load()
		var avgMs float64
		if ops > 0 {
			avgMs = float64(sm.totalNs.Load()) / float64(ops) / 1e6
		}
		result[name] = SceneSnapshot{
			Scene:      name,
			TotalOps:   ops,
			TotalErrs:  sm.errors.Load(),
			AvgLatency: time.Duration(int64(avgMs * float64(time.Millisecond))),
		}
	}
	return result
}

// SceneSnapshot holds a point-in-time view of a scene's metrics.
type SceneSnapshot struct {
	Scene      string
	TotalOps   int64
	TotalErrs  int64
	AvgLatency time.Duration
}

// LogSummary logs a summary of all scene metrics (for periodic reporting).
func (mc *MetricsCollector) LogSummary() {
	for name, snap := range mc.Snapshot() {
		log.Printf("redis metrics [scene=%s] ops=%d errs=%d avg_latency=%v",
			name, snap.TotalOps, snap.TotalErrs, snap.AvgLatency)
	}
}

// InstrumentedClient wraps a Client with per-operation metrics recording.
func InstrumentedClient(client Client, scene string, mc *MetricsCollector) Client {
	if mc == nil {
		return client
	}
	return &instrumentedClient{inner: client, scene: scene, mc: mc}
}

type instrumentedClient struct {
	inner Client
	scene string
	mc    *MetricsCollector
}

func (c *instrumentedClient) record(start time.Time, err error) {
	c.mc.Record(c.scene, time.Since(start), err)
}

func (c *instrumentedClient) Get(ctx context.Context, key string) (string, error) {
	t := time.Now()
	v, err := c.inner.Get(ctx, key)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) GetBytes(ctx context.Context, key string) ([]byte, error) {
	t := time.Now()
	v, err := c.inner.GetBytes(ctx, key)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	t := time.Now()
	err := c.inner.Set(ctx, key, value, ttl)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) SetBytes(ctx context.Context, key string, value []byte, ttl time.Duration) error {
	t := time.Now()
	err := c.inner.SetBytes(ctx, key, value, ttl)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) SetNX(ctx context.Context, key, value string, ttl time.Duration) (bool, error) {
	t := time.Now()
	v, err := c.inner.SetNX(ctx, key, value, ttl)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) Del(ctx context.Context, keys ...string) error {
	t := time.Now()
	err := c.inner.Del(ctx, keys...)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) Incr(ctx context.Context, key string) (int64, error) {
	t := time.Now()
	v, err := c.inner.Incr(ctx, key)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) Expire(ctx context.Context, key string, ttl time.Duration) error {
	t := time.Now()
	err := c.inner.Expire(ctx, key, ttl)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) HSet(ctx context.Context, key, field, value string) error {
	t := time.Now()
	err := c.inner.HSet(ctx, key, field, value)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) HGet(ctx context.Context, key, field string) (string, error) {
	t := time.Now()
	v, err := c.inner.HGet(ctx, key, field)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) HDel(ctx context.Context, key string, fields ...string) error {
	t := time.Now()
	err := c.inner.HDel(ctx, key, fields...)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	t := time.Now()
	v, err := c.inner.HGetAll(ctx, key)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) HIncrByFloat(ctx context.Context, key, field string, incr float64) error {
	t := time.Now()
	err := c.inner.HIncrByFloat(ctx, key, field, incr)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) SAdd(ctx context.Context, key string, members ...string) error {
	t := time.Now()
	err := c.inner.SAdd(ctx, key, members...)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) SMembers(ctx context.Context, key string) ([]string, error) {
	t := time.Now()
	v, err := c.inner.SMembers(ctx, key)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) SIsMember(ctx context.Context, key, member string) (bool, error) {
	t := time.Now()
	v, err := c.inner.SIsMember(ctx, key, member)
	c.record(t, err)
	return v, err
}

func (c *instrumentedClient) Publish(ctx context.Context, channel, message string) error {
	t := time.Now()
	err := c.inner.Publish(ctx, channel, message)
	c.record(t, err)
	return err
}

func (c *instrumentedClient) Subscribe(ctx context.Context, channels ...string) (Subscription, error) {
	return c.inner.Subscribe(ctx, channels...)
}

func (c *instrumentedClient) Pipeline(ctx context.Context) Pipeliner {
	return c.inner.Pipeline(ctx)
}

func (c *instrumentedClient) Close() error  { return c.inner.Close() }
func (c *instrumentedClient) Ping(ctx context.Context) error {
	t := time.Now()
	err := c.inner.Ping(ctx)
	c.record(t, err)
	return err
}
