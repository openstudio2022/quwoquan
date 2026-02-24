package testinfra

import (
	"context"
	"testing"

	"quwoquan_service/runtime/repository"
)

func TestMiniRedisCache(t *testing.T) {
	suite := NewSuite(t, WithRedis())
	defer suite.TearDown(t)

	cache := NewMiniRedisCache(suite.Redis)
	ctx := context.Background()

	if err := cache.Set(ctx, "test:key", []byte(`{"id":"1"}`), 60); err != nil {
		t.Fatalf("Set: %v", err)
	}

	data, err := cache.Get(ctx, "test:key")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if string(data) != `{"id":"1"}` {
		t.Errorf("got %q, want %q", string(data), `{"id":"1"}`)
	}

	if err := cache.Del(ctx, "test:key"); err != nil {
		t.Fatalf("Del: %v", err)
	}

	_, err = cache.Get(ctx, "test:key")
	if err == nil {
		t.Error("expected error after delete, got nil")
	}
}

func TestEventSpy(t *testing.T) {
	spy := NewEventSpy()

	spy.Publish(context.Background(), repository.DomainEvent{
		Type:          "PostCreated",
		AggregateType: "Post",
		AggregateID:   "p1",
		Payload:       map[string]any{"title": "hello"},
	})
	spy.Publish(context.Background(), repository.DomainEvent{
		Type:          "PostUpdated",
		AggregateType: "Post",
		AggregateID:   "p1",
		Payload:       map[string]any{"title": "updated"},
	})
	spy.Publish(context.Background(), repository.DomainEvent{
		Type:          "UserCreated",
		AggregateType: "UserProfile",
		AggregateID:   "u1",
	})

	if spy.Count() != 3 {
		t.Errorf("Count: got %d, want 3", spy.Count())
	}

	postEvents := spy.EventsOfType("PostCreated")
	if len(postEvents) != 1 {
		t.Errorf("PostCreated events: got %d, want 1", len(postEvents))
	}
	if postEvents[0].AggregateID != "p1" {
		t.Errorf("PostCreated aggregate ID: got %q, want %q", postEvents[0].AggregateID, "p1")
	}

	spy.Reset()
	if spy.Count() != 0 {
		t.Errorf("Count after reset: got %d, want 0", spy.Count())
	}
}

func TestSuiteCleanRedis(t *testing.T) {
	suite := NewSuite(t, WithRedis())
	defer suite.TearDown(t)

	suite.Redis.Set("k1", "v1")
	suite.Redis.Set("k2", "v2")

	suite.CleanRedis(t)

	if suite.Redis.Exists("k1") {
		t.Error("k1 should be flushed")
	}
	if suite.Redis.Exists("k2") {
		t.Error("k2 should be flushed")
	}
}
