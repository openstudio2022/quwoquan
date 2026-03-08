package redis

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/runtime/recommendation"
)

func TestCacheAdapter_GetSetDel(t *testing.T) {
	client := NewMemoryClient()
	adapter := NewCacheAdapter(client)
	ctx := context.Background()

	got, err := adapter.Get(ctx, "missing")
	if err != nil {
		t.Fatalf("Get missing: err=%v", err)
	}
	if got != nil {
		t.Errorf("Get missing: expected nil, got %v", got)
	}

	_ = adapter.Set(ctx, "k1", []byte("data"), 60)
	got, err = adapter.Get(ctx, "k1")
	if err != nil {
		t.Fatalf("Get after Set: err=%v", err)
	}
	if string(got) != "data" {
		t.Errorf("Get after Set: got %q, want %q", string(got), "data")
	}

	_ = adapter.Del(ctx, "k1")
	got, _ = adapter.Get(ctx, "k1")
	if got != nil {
		t.Errorf("Get after Del: expected nil, got %v", got)
	}
}

func TestRecAdapter_BasicOps(t *testing.T) {
	client := NewMemoryClient()
	rec := NewRecAdapter(client)
	ctx := context.Background()

	_ = rec.Set(ctx, "k1", "v1", time.Minute)
	v, err := rec.Get(ctx, "k1")
	if err != nil || v != "v1" {
		t.Errorf("Get/Set: got %q err=%v", v, err)
	}

	_ = rec.Del(ctx, "k1")
	_, err = rec.Get(ctx, "k1")
	if !errors.Is(err, ErrKeyNotFound) {
		t.Errorf("expected ErrKeyNotFound, got %v", err)
	}
}

func TestRecAdapter_SetOps(t *testing.T) {
	client := NewMemoryClient()
	rec := NewRecAdapter(client)
	ctx := context.Background()

	_ = rec.SAdd(ctx, "s1", "a", "b")
	members, _ := rec.SMembers(ctx, "s1")
	if len(members) != 2 {
		t.Errorf("SMembers: expected 2, got %d", len(members))
	}

	ok, _ := rec.SIsMember(ctx, "s1", "a")
	if !ok {
		t.Error("SIsMember should return true for 'a'")
	}
}

func TestRecAdapter_HashOps(t *testing.T) {
	client := NewMemoryClient()
	rec := NewRecAdapter(client)
	ctx := context.Background()

	_ = rec.HIncrByFloat(ctx, "h1", "score", 1.5)
	_ = rec.HIncrByFloat(ctx, "h1", "score", 2.0)

	all, _ := rec.HGetAll(ctx, "h1")
	if all["score"] == "" {
		t.Fatal("score should exist")
	}

	_ = rec.Expire(ctx, "h1", time.Minute)
}

func TestRecAdapter_PipelineRead(t *testing.T) {
	client := NewMemoryClient()
	rec := NewRecAdapter(client)
	ctx := context.Background()

	_ = rec.HIncrByFloat(ctx, "rec:session_signals:{u1}:s1", "travel", 5.0)
	_ = rec.SAdd(ctx, "rec:exposed:{u1}:s1", "p1", "p2")
	_ = rec.SAdd(ctx, "rec:negative:{u1}:s1", "p3")

	pipeliner, ok := rec.(recommendation.RedisPipeliner)
	if !ok {
		t.Fatal("RecAdapter should implement RedisPipeliner")
	}

	ops := []recommendation.PipelineOp{
		{Type: recommendation.PipelineHGetAll, Key: "rec:session_signals:{u1}:s1"},
		{Type: recommendation.PipelineSMembers, Key: "rec:exposed:{u1}:s1"},
		{Type: recommendation.PipelineSMembers, Key: "rec:negative:{u1}:s1"},
	}

	if err := pipeliner.PipelineRead(ctx, ops); err != nil {
		t.Fatalf("PipelineRead: %v", err)
	}

	if ops[0].Hash["travel"] == "" {
		t.Error("PipelineHGetAll should return travel field")
	}
	if len(ops[1].Set) != 2 {
		t.Errorf("exposed SMembers: expected 2, got %d", len(ops[1].Set))
	}
	if len(ops[2].Set) != 1 {
		t.Errorf("negative SMembers: expected 1, got %d", len(ops[2].Set))
	}
}

func TestRecAdapter_HotPathIntegration(t *testing.T) {
	client := NewMemoryClient()
	rec := NewRecAdapter(client)
	hp := recommendation.NewHotPath(rec)
	ctx := context.Background()

	signal := recommendation.BehaviorSignal{
		UserID:    "u1",
		SessionID: "s1",
		ContentID: "p1",
		Action:    "like",
		Tags:      []string{"travel"},
	}

	if err := hp.ProcessSignal(ctx, signal); err != nil {
		t.Fatalf("ProcessSignal: %v", err)
	}

	exposed, _ := hp.IsExposed(ctx, "u1", "s1", "p1")
	if !exposed {
		t.Error("p1 should be exposed after like signal")
	}

	state, err := hp.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatalf("GetSessionState: %v", err)
	}
	if state == nil {
		t.Fatal("session state should not be nil")
	}
	if len(state.ExposedIDs) != 1 {
		t.Errorf("expected 1 exposed ID, got %d", len(state.ExposedIDs))
	}
	if state.TagWeights["travel"] <= 0 {
		t.Error("travel tag weight should be positive after like")
	}
}
