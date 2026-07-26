package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	"strconv"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

type postProjectionSpy struct {
	events   []placementports.PostLifecycleEvent
	fail     bool
	attempts map[string]int64
}

func (spy *postProjectionSpy) ApplyPostLifecycle(_ context.Context, event placementports.PostLifecycleEvent) error {
	if spy.fail {
		return errors.New("projection unavailable")
	}
	spy.events = append(spy.events, event)
	return nil
}

func (spy *postProjectionSpy) RecordPostLifecycleFailure(_ context.Context, streamID, _ string, _ error) (int64, error) {
	if spy.attempts == nil {
		spy.attempts = map[string]int64{}
	}
	spy.attempts[streamID]++
	return spy.attempts[streamID], nil
}

func (spy *postProjectionSpy) ClearPostLifecycleFailure(_ context.Context, streamID string) error {
	delete(spy.attempts, streamID)
	return nil
}

func TestContentPostConsumerProjectsTypedStreamFactAndAcks(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	spy := &postProjectionSpy{}
	consumer := NewContentPostConsumer(
		newCircleTestMessageTransport(t, client), spy, spy, "test", nil,
	).WithDiscoveryFeedCache(client)
	if _, err := client.XAdd(ctx, ContentPostLifecycleStream, postLifecycleValues("evt-1", 2)); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("ProcessOnce count=%d err=%v", count, err)
	}
	if len(spy.events) != 1 || spy.events[0].PostID != "post-1" ||
		spy.events[0].OwnerPersonaID != "persona-1" || spy.events[0].PostVersion != 2 {
		t.Fatalf("typed event drift: %#v", spy.events)
	}
	if generation, err := client.Get(ctx, "cache:circle-discovery:generation"); err != nil || generation != "1" {
		t.Fatalf("post projection must invalidate discovery feed cache generation=%q err=%v", generation, err)
	}
	if err := consumer.Healthy(time.Second); err != nil {
		t.Fatalf("consumer must report a healthy completed scan: %v", err)
	}
}

func TestContentPostConsumerRecordsFailedProjection(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	spy := &postProjectionSpy{fail: true}
	consumer := NewContentPostConsumer(newCircleTestMessageTransport(t, client), spy, spy, "test", nil)
	if _, err := client.XAdd(ctx, ContentPostLifecycleStream, postLifecycleValues("evt-fail", 1)); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err == nil || count != 0 {
		t.Fatalf("failed projection must remain unacknowledged, count=%d err=%v", count, err)
	}
	if spy.attempts == nil || len(spy.attempts) != 1 {
		t.Fatalf("failed projection must record its durable delivery attempt: %#v", spy.attempts)
	}
}

func postLifecycleValues(eventID string, version int64) map[string]string {
	return map[string]string{
		"eventId": eventID, "eventType": "PostPublished", "aggregateType": "Post",
		"aggregateId": "post-1", "aggregateVersion": strconv.FormatInt(version, 10),
		"payload":    "{\"_id\":\"post-1\",\"authorId\":\"persona-1\",\"status\":\"published\"}",
		"occurredAt": time.Date(2026, 7, 14, 9, 0, 0, 0, time.UTC).Format(time.RFC3339Nano),
	}
}

func newCircleTestMessageTransport(
	t *testing.T,
	client rtredis.Client,
) *runtimemessaging.RedisMessageTransport {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"circle-service-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("new circle test message transport: %v", err)
	}
	return transport
}
