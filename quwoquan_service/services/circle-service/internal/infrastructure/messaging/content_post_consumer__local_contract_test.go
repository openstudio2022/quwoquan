package messaging

import (
	"context"
	"errors"
	"strconv"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
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
	consumer.minIdle = 0
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
	claimed, _, err := client.XAutoClaim(ctx, ContentPostLifecycleStream, contentPostConsumerGroup, "other", 0, "0-0", 10)
	if err != nil || len(claimed) != 0 {
		t.Fatalf("acked message remained pending: claimed=%d err=%v", len(claimed), err)
	}
}

func TestContentPostConsumerReclaimsAndDeadLettersAfterBoundedRetries(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	spy := &postProjectionSpy{fail: true}
	consumer := NewContentPostConsumer(newCircleTestMessageTransport(t, client), spy, spy, "test", nil)
	consumer.minIdle = 0
	if _, err := client.XAdd(ctx, ContentPostLifecycleStream, postLifecycleValues("evt-fail", 1)); err != nil {
		t.Fatal(err)
	}
	for attempt := int64(1); attempt <= contentPostMaxAttempts; attempt++ {
		_, err := consumer.ProcessOnce(ctx)
		if attempt < contentPostMaxAttempts && err == nil {
			t.Fatalf("attempt %d must remain failed and pending", attempt)
		}
		if attempt == contentPostMaxAttempts && err != nil {
			t.Fatalf("dead-letter attempt must complete transport handling: %v", err)
		}
	}
	if err := client.XGroupCreateMkStream(ctx, ContentPostLifecycleDLQ, "ops", "0"); err != nil {
		t.Fatal(err)
	}
	dlq, err := client.XReadGroup(ctx, "ops", "test", map[string]string{ContentPostLifecycleDLQ: ">"}, 10, 0)
	if err != nil || len(dlq) != 1 || dlq[0].Values["eventId"] != "evt-fail" {
		t.Fatalf("DLQ drift: %#v err=%v", dlq, err)
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
