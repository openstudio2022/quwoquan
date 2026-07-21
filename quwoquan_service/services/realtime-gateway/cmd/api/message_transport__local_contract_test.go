package main

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
)

func TestRequireMessageTransportBuildsDescriptorBoundTransport(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "realtime",
	})
	defer router.Close()

	transport, err := requireMessageTransport(
		context.Background(),
		"alpha",
		router,
		map[string]string{"realtime": "memory"},
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
		map[string]string{"realtime": "memory"},
	); err == nil {
		t.Fatal("beta message transport error = nil, want fail-closed")
	}
}
