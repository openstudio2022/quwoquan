package recommendation

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

func TestSearchSignalConsumerProjectsAndAcks(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	projector := &recordingSearchProjector{}
	consumer := NewSearchSignalConsumer(redis, projector, "worker-1", nil)

	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, SearchRecommendationSignalStream, map[string]string{
		"searchRequestId":     "req-1",
		"userId":              "user-1",
		"sessionId":           "sess-1",
		"query":               "成都火锅",
		"normalizedQuery":     "成都 火锅",
		"relatedTerms":        `["川菜","美食"]`,
		"topClickedObjectIds": `["post-1"]`,
		"resultCount":         "7",
		"createdAt":           time.Date(2026, 6, 16, 10, 0, 0, 0, time.UTC).Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("XAdd: %v", err)
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("ProcessOnce: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d want 1", processed)
	}
	if len(projector.events) != 1 {
		t.Fatalf("projected events=%d want 1", len(projector.events))
	}
	got := projector.events[0]
	if got.Type != "SearchRecommendationSignalPublished" || got.AggregateID != "req-1" {
		t.Fatalf("event identity=%+v", got)
	}
	if got.Payload["userId"] != "user-1" || got.Payload["normalizedQuery"] != "成都 火锅" {
		t.Fatalf("payload=%#v", got.Payload)
	}
	terms, _ := got.Payload["relatedTerms"].([]string)
	if len(terms) != 2 || terms[0] != "川菜" {
		t.Fatalf("relatedTerms=%v", terms)
	}
	pending, err := redis.XReadGroup(ctx, searchSignalConsumerGroup, "worker-1", map[string]string{SearchRecommendationSignalStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("pending read: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d want 0", len(pending))
	}
}

type recordingSearchProjector struct {
	events []ProjectorEvent
}

func (r *recordingSearchProjector) Project(_ context.Context, event ProjectorEvent) error {
	r.events = append(r.events, event)
	return nil
}
