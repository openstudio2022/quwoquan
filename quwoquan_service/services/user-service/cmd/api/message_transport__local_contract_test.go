package main

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
)

func TestNewUserMessageTransportPreflightsGeneratedBinding(t *testing.T) {
	t.Parallel()

	cfg := config{}
	cfg.Redis.General.Mode = "memory"
	cfg.Redis.Realtime.Mode = "memory"
	router := buildRedisRouter(cfg)
	defer router.Close()

	transport, err := newUserMessageTransport(context.Background(), "alpha", router, cfg)
	if err != nil {
		t.Fatalf("alpha message transport preflight error = %v", err)
	}
	if transport == nil {
		t.Fatal("alpha message transport = nil")
	}
}

func TestNewUserMessageTransportFailsClosedForBlockedReleaseBinding(t *testing.T) {
	t.Parallel()

	cfg := config{}
	cfg.Redis.General.Mode = "memory"
	cfg.Redis.Realtime.Mode = "memory"
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	defer router.Close()

	if _, err := newUserMessageTransport(context.Background(), "beta", router, cfg); err == nil {
		t.Fatal("blocked beta message transport preflight error = nil, want fail-closed")
	}
}
