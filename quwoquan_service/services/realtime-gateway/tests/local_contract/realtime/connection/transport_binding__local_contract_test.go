package local_contract

import (
	"context"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

func TestRealtimeTransportBindingUsesRuntimeDescriptor(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes:       map[string]rtredis.SceneConfig{"realtime": {Mode: "memory"}},
		DefaultScene: "realtime",
	})
	defer router.Close()

	root := runtimemessaging.MessageTransportRoot{
		RootID:              "realtime-gateway-api",
		RequiredRedisScenes: []string{"realtime"},
	}
	binding := runtimemessaging.MessageTransportBinding{
		State:               "enabled",
		AdapterID:           runtimemessaging.RedisMessageTransportFixture,
		TimeoutMilliseconds: 100,
	}
	if transport, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"alpha",
		true,
		binding,
		root,
		router,
		map[string]string{"realtime": "memory"},
	); err != nil {
		t.Fatalf("alpha fixture transport = %v, %v", transport, err)
	} else if _, ok := transport.Scene("realtime"); !ok {
		t.Fatal("alpha transport does not expose its required scene")
	}
	if _, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		context.Background(),
		"gamma",
		true,
		binding,
		root,
		router,
		map[string]string{"realtime": "memory"},
	); err == nil {
		t.Fatal("non-alpha fixture must fail closed")
	}
}
