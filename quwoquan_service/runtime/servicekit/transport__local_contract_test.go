package servicekit

import (
	"context"
	"strings"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

func fixtureTransportSpec(scenes ...string) MessageTransportSpec {
	return MessageTransportSpec{
		RootID:       "circle-service-api",
		BindingFound: true,
		Binding: runtimemessaging.MessageTransportBinding{
			State:               "enabled",
			AdapterID:           runtimemessaging.RedisMessageTransportFixture,
			TimeoutMilliseconds: 1000,
		},
		RequiredRedisScenes: scenes,
	}
}

func fixtureRouter(t *testing.T, scenes ...string) (*rtredis.Router, map[string]string) {
	t.Helper()
	sceneConfigs := make(map[string]RedisSceneConfig, len(scenes))
	for _, scene := range scenes {
		sceneConfigs[scene] = RedisSceneConfig{Mode: "memory"}
	}
	built, modes, err := NewRedisRouter(sceneConfigs)
	if err != nil {
		t.Fatalf("router build failed: %v", err)
	}
	return built, modes
}

func TestNewMessageTransportRequiresRootID(t *testing.T) {
	spec := fixtureTransportSpec("general")
	spec.RootID = " "
	_, err := NewMessageTransport(context.Background(), "alpha", spec, nil, nil)
	if err == nil || !strings.Contains(err.Error(), "root ID") {
		t.Fatalf("expected root ID requirement, got %v", err)
	}
}

func TestNewMessageTransportFailsClosedWhenBindingMissing(t *testing.T) {
	spec := fixtureTransportSpec("general")
	spec.BindingFound = false
	router, modes := fixtureRouter(t, "general")
	_, err := NewMessageTransport(context.Background(), "alpha", spec, router, modes)
	if err == nil || !strings.Contains(err.Error(), "binding is missing") {
		t.Fatalf("expected missing binding failure, got %v", err)
	}
}

func TestNewMessageTransportRequiresExactlyOneScene(t *testing.T) {
	spec := fixtureTransportSpec("general", "cache")
	router, modes := fixtureRouter(t, "general", "cache")
	_, err := NewMessageTransport(context.Background(), "alpha", spec, router, modes)
	if err == nil || !strings.Contains(err.Error(), "exactly one Redis scene") {
		t.Fatalf("expected single-scene contract failure, got %v", err)
	}
}

func TestNewMessageTransportRejectsFixtureOutsideAlpha(t *testing.T) {
	spec := fixtureTransportSpec("general")
	router, modes := fixtureRouter(t, "general")
	_, err := NewMessageTransport(context.Background(), "prod", spec, router, modes)
	if err == nil || !strings.Contains(err.Error(), "only in alpha") {
		t.Fatalf("expected fixture environment rejection, got %v", err)
	}
}

func TestNewMessageTransportBuildsFixtureTransportInAlpha(t *testing.T) {
	spec := fixtureTransportSpec("general")
	router, modes := fixtureRouter(t, "general")
	transport, err := NewMessageTransport(context.Background(), "alpha", spec, router, modes)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if transport == nil {
		t.Fatal("expected a constructed transport")
	}
}
