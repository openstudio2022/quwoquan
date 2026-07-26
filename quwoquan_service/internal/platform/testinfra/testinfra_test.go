// spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-001
package testinfra

import (
	"context"
	"testing"

	messaging "quwoquan_service/runtime/messaging"
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

	spy.Publish(context.Background(), messaging.DomainEvent{
		Type:          "PostCreated",
		AggregateType: "Post",
		AggregateID:   "p1",
		Payload:       map[string]any{"title": "hello"},
	})
	spy.Publish(context.Background(), messaging.DomainEvent{
		Type:          "PostUpdated",
		AggregateType: "Post",
		AggregateID:   "p1",
		Payload:       map[string]any{"title": "updated"},
	})
	spy.Publish(context.Background(), messaging.DomainEvent{
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

func TestPostgresFixtureReusesOneProcessAndCleansBetweenSuites(t *testing.T) {
	fixture, err := StartPostgresFixture(t.TempDir(), 0)
	if err != nil {
		t.Fatalf("start shared postgres fixture: %v", err)
	}
	defer func() {
		if err := fixture.Close(); err != nil {
			t.Fatalf("close shared postgres fixture: %v", err)
		}
	}()

	first := NewSuite(t, WithPostgresFixture(fixture))
	if _, err := first.PG.Exec(`CREATE TABLE shared_fixture_probe (id TEXT PRIMARY KEY)`); err != nil {
		t.Fatalf("create shared fixture probe: %v", err)
	}
	if _, err := first.PG.Exec(`INSERT INTO shared_fixture_probe (id) VALUES ('first')`); err != nil {
		t.Fatalf("seed shared fixture probe: %v", err)
	}
	first.TearDown(t)

	second := NewSuite(t, WithPostgresFixture(fixture))
	defer second.TearDown(t)
	var count int
	if err := second.PG.QueryRow(`SELECT COUNT(*) FROM shared_fixture_probe`).Scan(&count); err != nil {
		t.Fatalf("read shared fixture probe after cleanup: %v", err)
	}
	if count != 0 {
		t.Fatalf("shared fixture leaked %d rows between suites", count)
	}
}
