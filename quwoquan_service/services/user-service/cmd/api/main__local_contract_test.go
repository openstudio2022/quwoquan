package main

import (
	"context"
	"testing"
	"time"
)

func TestBuildRedisRouterProvidesRealtimeFallback(t *testing.T) {
	cfg := config{}
	cfg.Redis.General.Mode = "memory"

	router := buildRedisRouter(cfg)
	defer router.Close()

	ctx := context.Background()
	if err := router.Scene("realtime").Set(ctx, "sync:test", "ok", time.Minute); err != nil {
		t.Fatalf("realtime set: %v", err)
	}
	got, err := router.Scene("realtime").Get(ctx, "sync:test")
	if err != nil {
		t.Fatalf("realtime get: %v", err)
	}
	if got != "ok" {
		t.Fatalf("realtime get = %q, want %q", got, "ok")
	}
}
