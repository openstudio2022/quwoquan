package local_contract

import (
	"context"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

func TestNotificationMessageTransportBindingIsDescriptorBoundAndFailsClosed(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes:       map[string]rtredis.SceneConfig{"general": {Mode: "memory"}},
		DefaultScene: "general",
	})
	defer router.Close()

	root := runtimemessaging.MessageTransportRoot{
		RootID:              "notification-service-api",
		RequiredRedisScenes: []string{"general"},
	}
	fixture := runtimemessaging.MessageTransportBinding{
		State:               "enabled",
		AdapterID:           runtimemessaging.RedisMessageTransportFixture,
		TimeoutMilliseconds: 100,
	}
	if transport, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"alpha",
		true,
		fixture,
		root,
		router,
		map[string]string{"general": "memory"},
	); err != nil {
		t.Fatalf("alpha fixture transport = %v, %v", transport, err)
	} else if _, ok := transport.Scene("general"); !ok {
		t.Fatal("alpha transport does not expose its required scene")
	}
	if _, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"beta",
		true,
		fixture,
		root,
		router,
		map[string]string{"general": "memory"},
	); err == nil {
		t.Fatal("non-alpha memory fixture must fail closed")
	}
}
