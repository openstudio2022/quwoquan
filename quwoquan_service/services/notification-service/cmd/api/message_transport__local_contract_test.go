package main

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
)

func TestRequireNotificationAPIMessageTransportUsesGeneratedBindingAndFailsClosed(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	defer router.Close()

	sceneModes := map[string]string{
		"general":  "memory",
		"realtime": "memory",
	}
	transport, err := requireNotificationAPIMessageTransport(
		context.Background(),
		"alpha",
		router,
		sceneModes,
	)
	if err != nil {
		t.Fatalf("alpha fixture message transport: %v", err)
	}
	if transport == nil {
		t.Fatal("alpha fixture message transport is nil")
	}

	if _, err := requireNotificationAPIMessageTransport(
		context.Background(),
		"beta",
		router,
		sceneModes,
	); err == nil {
		t.Fatal("beta blocked generated binding did not fail closed")
	}
}
