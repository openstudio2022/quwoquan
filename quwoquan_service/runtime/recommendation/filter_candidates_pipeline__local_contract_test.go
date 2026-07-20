package recommendation

// N3-2 契约：FilterCandidates 的 pipeline 路径（RedisPipeliner 单 RTT 批量
// SISMEMBER）与逐条回退路径语义逐位一致——negative 拦截、served/impressed
// 双轨重复曝光过滤、空 contentID 跳过。防止两条路径漂移成第二真相源。

import (
	"context"
	"testing"
	"time"
)

// plainRedis 剥掉 PipelineRead，强制 FilterCandidates 走逐条回退路径。
type plainRedis struct{ inner *mockRedisClient }

func (p plainRedis) Get(ctx context.Context, key string) (string, error) {
	return p.inner.Get(ctx, key)
}
func (p plainRedis) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	return p.inner.Set(ctx, key, value, ttl)
}
func (p plainRedis) SetNX(ctx context.Context, key, value string, ttl time.Duration) (bool, error) {
	return p.inner.SetNX(ctx, key, value, ttl)
}
func (p plainRedis) Del(ctx context.Context, keys ...string) error {
	return p.inner.Del(ctx, keys...)
}
func (p plainRedis) HIncrByFloat(ctx context.Context, key, field string, incr float64) error {
	return p.inner.HIncrByFloat(ctx, key, field, incr)
}
func (p plainRedis) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return p.inner.HGetAll(ctx, key)
}
func (p plainRedis) SAdd(ctx context.Context, key string, members ...string) error {
	return p.inner.SAdd(ctx, key, members...)
}
func (p plainRedis) SRem(ctx context.Context, key string, members ...string) error {
	return p.inner.SRem(ctx, key, members...)
}
func (p plainRedis) SMembers(ctx context.Context, key string) ([]string, error) {
	return p.inner.SMembers(ctx, key)
}
func (p plainRedis) SIsMember(ctx context.Context, key, member string) (bool, error) {
	return p.inner.SIsMember(ctx, key, member)
}
func (p plainRedis) Expire(ctx context.Context, key string, ttl time.Duration) error {
	return p.inner.Expire(ctx, key, ttl)
}

func seedFilterFixture(t *testing.T, processor SignalProcessor, memory ExposureMemory) {
	t.Helper()
	ctx := context.Background()
	if err := memory.RecordServed(ctx, "u1", []FeedItem{{ContentID: "c_served"}}, time.Now()); err != nil {
		t.Fatalf("record served: %v", err)
	}
	if err := memory.RecordImpressed(ctx, "u1", "c_impressed", time.Now()); err != nil {
		t.Fatalf("record impressed: %v", err)
	}
	if err := processor.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c_neg", Action: "dislike",
	}); err != nil {
		t.Fatalf("process dislike: %v", err)
	}
}

func filterFixtureCandidates() []ContentCandidate {
	return []ContentCandidate{
		{ContentID: "c_neg"},
		{ContentID: "c_served"},
		{ContentID: "c_impressed"},
		{ContentID: ""},
		{ContentID: "c_ok"},
	}
}

func assertFilterSemantics(t *testing.T, filtered []ContentCandidate, label string) {
	t.Helper()
	// 两条路径语义一致：negative/served/impressed 命中被过滤；空 contentID
	// 候选同样被丢弃（逐条与 pipeline 路径都 continue 跳过）。
	if len(filtered) != 1 {
		t.Fatalf("%s: want exactly c_ok to survive, got %+v", label, filtered)
	}
	if filtered[0].ContentID != "c_ok" {
		t.Fatalf("%s: c_ok must survive, got %+v", label, filtered)
	}
}

func TestFilterCandidates_PipelineAndFallbackPathsAgree(t *testing.T) {
	ctx := context.Background()

	// pipeline 路径（mockRedisClient 实现 RedisPipeliner）。
	pipelineHP := NewHotPath(newMockRedis())
	seedFilterFixture(t, pipelineHP, pipelineHP)
	pipelineOut, err := pipelineHP.FilterCandidates(ctx, "u1", filterFixtureCandidates(), time.Now())
	if err != nil {
		t.Fatalf("pipeline path: %v", err)
	}
	assertFilterSemantics(t, pipelineOut, "pipeline path")

	// 逐条回退路径（plainRedis 不实现 RedisPipeliner）。
	fallbackHP := NewHotPath(plainRedis{inner: newMockRedis()})
	seedFilterFixture(t, fallbackHP, fallbackHP)
	fallbackOut, err := fallbackHP.FilterCandidates(ctx, "u1", filterFixtureCandidates(), time.Now())
	if err != nil {
		t.Fatalf("fallback path: %v", err)
	}
	assertFilterSemantics(t, fallbackOut, "fallback path")
}
