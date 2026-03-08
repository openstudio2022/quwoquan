package tests

import (
	"context"
	"errors"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

func TestRedisRouter_DualSceneIsolation(t *testing.T) {
	if testRouter == nil {
		t.Skip("testRouter not initialized")
	}
	ctx := context.Background()

	rec := testRouter.Scene("rec")
	gen := testRouter.Scene("general")

	_ = rec.Set(ctx, "rec:isolation:k1", "rec-only", time.Minute)
	_ = gen.Set(ctx, "cache:isolation:k1", "gen-only", time.Minute)

	v1, err := rec.Get(ctx, "rec:isolation:k1")
	if err != nil || v1 != "rec-only" {
		t.Errorf("rec scene: got %q err=%v", v1, err)
	}

	_, err = gen.Get(ctx, "rec:isolation:k1")
	if !errors.Is(err, rtredis.ErrKeyNotFound) {
		t.Errorf("general scene should not have rec key, err=%v", err)
	}

	v2, err := gen.Get(ctx, "cache:isolation:k1")
	if err != nil || v2 != "gen-only" {
		t.Errorf("general scene: got %q err=%v", v2, err)
	}

	_, err = rec.Get(ctx, "cache:isolation:k1")
	if !errors.Is(err, rtredis.ErrKeyNotFound) {
		t.Errorf("rec scene should not have general key, err=%v", err)
	}
}

func TestRedisRouter_PrefixRoutingToCorrectScene(t *testing.T) {
	if testRouter == nil {
		t.Skip("testRouter not initialized")
	}
	ctx := context.Background()

	recKey := "rec:session_signals:{test_user}:test_session"
	genKey := "cache:post:test_post"

	_ = testRouter.ForKey(recKey).Set(ctx, recKey, "rec-data", time.Minute)
	_ = testRouter.ForKey(genKey).Set(ctx, genKey, "gen-data", time.Minute)

	v1, _ := testRouter.Scene("rec").Get(ctx, recKey)
	if v1 != "rec-data" {
		t.Errorf("rec prefix route: got %q, want %q", v1, "rec-data")
	}

	v2, _ := testRouter.Scene("general").Get(ctx, genKey)
	if v2 != "gen-data" {
		t.Errorf("general prefix route: got %q, want %q", v2, "gen-data")
	}
}

func TestRedisRouter_RecSceneBacksMiniredis(t *testing.T) {
	if testRouter == nil {
		t.Skip("testRouter not initialized")
	}
	ctx := context.Background()

	rec := testRouter.Scene("rec")

	if err := rec.Ping(ctx); err != nil {
		t.Fatalf("rec scene Ping: %v (should be backed by miniredis)", err)
	}

	_ = rec.Set(ctx, "rec:test:ping", "alive", time.Second)
	v, err := rec.Get(ctx, "rec:test:ping")
	if err != nil || v != "alive" {
		t.Errorf("rec scene Get/Set via miniredis: got %q err=%v", v, err)
	}
}

func TestRedisRouter_GeneralSceneBacksMemory(t *testing.T) {
	if testRouter == nil {
		t.Skip("testRouter not initialized")
	}
	ctx := context.Background()

	gen := testRouter.Scene("general")

	if err := gen.Ping(ctx); err != nil {
		t.Fatalf("general scene Ping: %v", err)
	}

	_ = gen.Set(ctx, "cache:test:ping", "alive", time.Second)
	v, err := gen.Get(ctx, "cache:test:ping")
	if err != nil || v != "alive" {
		t.Errorf("general scene Get/Set via memory: got %q err=%v", v, err)
	}
}
