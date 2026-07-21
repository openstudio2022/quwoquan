package main

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
)

func TestRequireSearchAPIMessageTransportUsesGeneratedBindingAndFailsClosed(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	defer router.Close()

	sceneModes := map[string]string{"general": "memory"}
	transport, err := requireSearchAPIMessageTransport(
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

	if _, err := requireSearchAPIMessageTransport(
		context.Background(),
		"beta",
		router,
		sceneModes,
	); err == nil {
		t.Fatal("beta blocked generated binding did not fail closed")
	}
}
