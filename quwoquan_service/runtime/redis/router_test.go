package redis

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestRouter_SceneIsolation(t *testing.T) {
	router := MustNewRouter(DefaultRouterConfig())
	defer router.Close()
	ctx := context.Background()

	rec := router.Scene("rec")
	gen := router.Scene("general")
	rt := router.Scene("realtime")

	_ = rec.Set(ctx, "k1", "rec-val", time.Minute)
	_ = gen.Set(ctx, "k1", "gen-val", time.Minute)
	_ = rt.Set(ctx, "k1", "rt-val", time.Minute)

	v1, _ := rec.Get(ctx, "k1")
	v2, _ := gen.Get(ctx, "k1")
	v3, _ := rt.Get(ctx, "k1")

	if v1 != "rec-val" {
		t.Errorf("rec scene: got %q, want %q", v1, "rec-val")
	}
	if v2 != "gen-val" {
		t.Errorf("general scene: got %q, want %q", v2, "gen-val")
	}
	if v3 != "rt-val" {
		t.Errorf("realtime scene: got %q, want %q", v3, "rt-val")
	}
}

func TestRouter_PrefixRouting(t *testing.T) {
	router := MustNewRouter(DefaultRouterConfig())
	defer router.Close()
	ctx := context.Background()

	_ = router.ForKey("rec:session_signals:{u1}:s1").Set(ctx, "rec:session_signals:{u1}:s1", "sig", time.Minute)
	_ = router.ForKey("cache:post:p1").Set(ctx, "cache:post:p1", "cached", time.Minute)
	_ = router.ForKey("seq:conversation:c1").Set(ctx, "seq:conversation:c1", "42", time.Minute)

	v1, _ := router.Scene("rec").Get(ctx, "rec:session_signals:{u1}:s1")
	if v1 != "sig" {
		t.Errorf("rec prefix route: got %q, want %q", v1, "sig")
	}

	v2, _ := router.Scene("general").Get(ctx, "cache:post:p1")
	if v2 != "cached" {
		t.Errorf("general prefix route: got %q, want %q", v2, "cached")
	}

	v3, _ := router.Scene("realtime").Get(ctx, "seq:conversation:c1")
	if v3 != "42" {
		t.Errorf("realtime prefix route: got %q, want %q", v3, "42")
	}
}

func TestRouter_DefaultSceneFallback(t *testing.T) {
	router := MustNewRouter(DefaultRouterConfig())
	defer router.Close()
	ctx := context.Background()

	_ = router.ForKey("unknown:prefix:k1").Set(ctx, "unknown:prefix:k1", "fallback", time.Minute)

	v, _ := router.Scene("general").Get(ctx, "unknown:prefix:k1")
	if v != "fallback" {
		t.Errorf("default scene fallback: got %q, want %q", v, "fallback")
	}
}

func TestRouter_LongestPrefixMatch(t *testing.T) {
	cfg := RouterConfig{
		Scenes: map[string]SceneConfig{
			"a": {Mode: "memory"},
			"b": {Mode: "memory"},
		},
		PrefixRoutes: []PrefixRoute{
			{Prefix: "cache:", Scene: "a"},
			{Prefix: "cache:hot:", Scene: "b"},
		},
		DefaultScene: "a",
	}
	router := MustNewRouter(cfg)
	defer router.Close()
	ctx := context.Background()

	_ = router.ForKey("cache:hot:k1").Set(ctx, "cache:hot:k1", "hot-val", time.Minute)

	vb, _ := router.Scene("b").Get(ctx, "cache:hot:k1")
	if vb != "hot-val" {
		t.Errorf("longest prefix match to scene b: got %q, want %q", vb, "hot-val")
	}

	va, err := router.Scene("a").Get(ctx, "cache:hot:k1")
	if !errors.Is(err, ErrKeyNotFound) && va != "" {
		t.Errorf("scene a should not have the key, got %q", va)
	}
}

func TestRouter_Scenes(t *testing.T) {
	router := MustNewRouter(DefaultRouterConfig())
	defer router.Close()

	names := router.Scenes()
	if len(names) != 3 {
		t.Fatalf("expected 3 scenes, got %d: %v", len(names), names)
	}
	expected := map[string]bool{"general": true, "rec": true, "realtime": true}
	for _, n := range names {
		if !expected[n] {
			t.Errorf("unexpected scene %q", n)
		}
	}
}

func TestRouter_UnknownScenePanics(t *testing.T) {
	router := MustNewRouter(DefaultRouterConfig())
	defer router.Close()

	defer func() {
		if r := recover(); r == nil {
			t.Error("expected panic on unknown scene")
		}
	}()
	router.Scene("nonexistent")
}

func TestRouter_InvalidConfigErrors(t *testing.T) {
	_, err := NewRouter(RouterConfig{})
	if err == nil {
		t.Error("expected error for empty scenes")
	}

	_, err = NewRouter(RouterConfig{
		Scenes:       map[string]SceneConfig{"a": {Mode: "memory"}},
		PrefixRoutes: []PrefixRoute{{Prefix: "x:", Scene: "missing"}},
		DefaultScene: "a",
	})
	if err == nil {
		t.Error("expected error for prefix route referencing unknown scene")
	}

	_, err = NewRouter(RouterConfig{
		Scenes:       map[string]SceneConfig{"a": {Mode: "memory"}},
		DefaultScene: "missing",
	})
	if err == nil {
		t.Error("expected error for missing default scene")
	}
}

func TestMemoryClient_StringOps(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	_, err := c.Get(ctx, "k1")
	if !errors.Is(err, ErrKeyNotFound) {
		t.Errorf("expected ErrKeyNotFound, got %v", err)
	}

	_ = c.Set(ctx, "k1", "v1", time.Minute)
	v, err := c.Get(ctx, "k1")
	if err != nil || v != "v1" {
		t.Errorf("Get after Set: got %q err=%v", v, err)
	}

	_ = c.Del(ctx, "k1")
	_, err = c.Get(ctx, "k1")
	if !errors.Is(err, ErrKeyNotFound) {
		t.Errorf("expected ErrKeyNotFound after Del, got %v", err)
	}
}

func TestMemoryClient_SetNX(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	ok, _ := c.SetNX(ctx, "k1", "first", time.Minute)
	if !ok {
		t.Error("first SetNX should succeed")
	}

	ok, _ = c.SetNX(ctx, "k1", "second", time.Minute)
	if ok {
		t.Error("second SetNX should fail")
	}

	v, _ := c.Get(ctx, "k1")
	if v != "first" {
		t.Errorf("value should be first, got %q", v)
	}
}

func TestMemoryClient_Incr(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	n, _ := c.Incr(ctx, "counter")
	if n != 1 {
		t.Errorf("first Incr: got %d, want 1", n)
	}
	n, _ = c.Incr(ctx, "counter")
	if n != 2 {
		t.Errorf("second Incr: got %d, want 2", n)
	}
}

func TestMemoryClient_HashOps(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	_ = c.HSet(ctx, "h1", "f1", "v1")
	_ = c.HSet(ctx, "h1", "f2", "v2")

	v, _ := c.HGet(ctx, "h1", "f1")
	if v != "v1" {
		t.Errorf("HGet: got %q, want v1", v)
	}

	all, _ := c.HGetAll(ctx, "h1")
	if len(all) != 2 {
		t.Errorf("HGetAll: expected 2 fields, got %d", len(all))
	}

	_ = c.HDel(ctx, "h1", "f1")
	_, err := c.HGet(ctx, "h1", "f1")
	if !errors.Is(err, ErrKeyNotFound) {
		t.Error("expected ErrKeyNotFound after HDel")
	}
}

func TestMemoryClient_SetOps(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	_ = c.SAdd(ctx, "s1", "a", "b", "c")
	members, _ := c.SMembers(ctx, "s1")
	if len(members) != 3 {
		t.Errorf("SMembers: expected 3, got %d", len(members))
	}

	ok, _ := c.SIsMember(ctx, "s1", "b")
	if !ok {
		t.Error("SIsMember: b should be a member")
	}

	ok, _ = c.SIsMember(ctx, "s1", "z")
	if ok {
		t.Error("SIsMember: z should not be a member")
	}
}

func TestMemoryClient_PubSub(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	sub, _ := c.Subscribe(ctx, "ch1")
	defer sub.Close()

	ch := sub.Channel()

	_ = c.Publish(ctx, "ch1", "hello")
	msg := <-ch
	if msg.Channel != "ch1" || msg.Payload != "hello" {
		t.Errorf("PubSub: got channel=%q payload=%q", msg.Channel, msg.Payload)
	}
}

func TestMemoryClient_Pipeline(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	_ = c.Set(ctx, "pk1", "pv1", time.Minute)
	_ = c.HSet(ctx, "ph1", "f1", "hv1")
	_ = c.SAdd(ctx, "ps1", "m1", "m2")

	pipe := c.Pipeline(ctx)
	gr := pipe.Get(ctx, "pk1")
	hr := pipe.HGetAll(ctx, "ph1")
	sr := pipe.SMembers(ctx, "ps1")

	if err := pipe.Exec(ctx); err != nil {
		t.Fatalf("Pipeline exec: %v", err)
	}

	gv, _ := gr.Result()
	if gv != "pv1" {
		t.Errorf("Pipeline Get: got %q, want pv1", gv)
	}

	hv, _ := hr.Result()
	if hv["f1"] != "hv1" {
		t.Errorf("Pipeline HGetAll: got %v", hv)
	}

	sv, _ := sr.Result()
	if len(sv) != 2 {
		t.Errorf("Pipeline SMembers: got %d, want 2", len(sv))
	}
}

func TestMemoryClient_PingAndClose(t *testing.T) {
	c := NewMemoryClient()
	if err := c.Ping(context.Background()); err != nil {
		t.Errorf("Ping: %v", err)
	}
	if err := c.Close(); err != nil {
		t.Errorf("Close: %v", err)
	}
}

func TestMemoryClient_HIncrByFloat(t *testing.T) {
	c := NewMemoryClient()
	ctx := context.Background()

	_ = c.HIncrByFloat(ctx, "h1", "score", 1.5)
	_ = c.HIncrByFloat(ctx, "h1", "score", 2.3)

	all, _ := c.HGetAll(ctx, "h1")
	v := all["score"]
	if v == "" {
		t.Fatal("score field should exist")
	}
}

func TestInstrumentedClient(t *testing.T) {
	inner := NewMemoryClient()
	mc := NewMetricsCollector([]string{"test"})
	client := InstrumentedClient(inner, "test", mc)

	ctx := context.Background()
	_ = client.Set(ctx, "k1", "v1", time.Minute)
	_, _ = client.Get(ctx, "k1")

	snap := mc.Snapshot()
	if snap["test"].TotalOps != 2 {
		t.Errorf("expected 2 ops, got %d", snap["test"].TotalOps)
	}
}
