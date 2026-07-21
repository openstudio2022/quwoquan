package main

import (
	"context"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

func TestRequireMessageTransportDescriptorFailsClosedOutsideAlphaFixture(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	defer router.Close()

	root := runtimemessaging.MessageTransportRoot{
		RootID:              "product-ops-service-api",
		RequiredRedisScenes: []string{"general"},
	}
	fixture := runtimemessaging.MessageTransportBinding{
		State:               "enabled",
		AdapterID:           runtimemessaging.RedisMessageTransportFixture,
		TimeoutMilliseconds: 100,
	}
	if _, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"alpha",
		true,
		fixture,
		root,
		router,
		map[string]string{"general": "memory"},
	); err != nil {
		t.Fatalf("alpha fixture preflight error = %v", err)
	}

	if _, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"beta",
		true,
		runtimemessaging.MessageTransportBinding{
			State:               "enabled",
			AdapterID:           runtimemessaging.RedisMessageTransportAdapter,
			TimeoutMilliseconds: 100,
		},
		root,
		router,
		map[string]string{"general": "memory"},
	); err == nil {
		t.Fatal("beta memory transport preflight error = nil, want fail-closed")
	}

	if _, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"beta",
		true,
		fixture,
		root,
		router,
		map[string]string{"general": "standalone"},
	); err == nil {
		t.Fatal("beta fixture transport preflight error = nil, want fail-closed")
	}

	if _, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"beta",
		true,
		runtimemessaging.MessageTransportBinding{
			State:               "blocked",
			AdapterID:           runtimemessaging.RedisMessageTransportAdapter,
			TimeoutMilliseconds: 100,
		},
		root,
		router,
		map[string]string{"general": "standalone"},
	); err == nil {
		t.Fatal("blocked transport preflight error = nil, want fail-closed")
	}
}

func TestRequireMessageTransportBuildsDescriptorBoundTransport(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	defer router.Close()

	transport, err := requireMessageTransport(
		context.Background(),
		"alpha",
		router,
		map[string]string{"general": "memory"},
	)
	if err != nil {
		t.Fatalf("alpha message transport = %v", err)
	}
	if transport == nil {
		t.Fatal("alpha message transport = nil")
	}

	if _, err := requireMessageTransport(
		context.Background(),
		"beta",
		router,
		map[string]string{"general": "memory"},
	); err == nil {
		t.Fatal("beta message transport error = nil, want fail-closed")
	}
}
