package recommendation_test

import (
	"context"
	"errors"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
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
		"signalId":         "query:req-1",
		"signalType":       "query",
		"searchRequestId":  "req-1",
		"userId":           "user-1",
		"sessionId":        "sess-1",
		"normalizedQuery":  "成都 火锅",
		"relatedTerms":     `["川菜","美食"]`,
		"engagedObjectIds": `[]`,
		"resultCount":      "7",
		"createdAt":        time.Date(2026, 6, 16, 10, 0, 0, 0, time.UTC).Format(time.RFC3339Nano),
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
	pending, err := redis.XReadGroup(ctx, SearchSignalConsumerGroup, "worker-1", map[string]string{SearchRecommendationSignalStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("pending read: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d want 0", len(pending))
	}
}

func TestSearchSignalConsumerQuarantinesMalformedWithoutRawPayload(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	consumer := NewSearchSignalConsumer(redis, &recordingSearchProjector{}, "worker-malformed", nil)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, SearchRecommendationSignalStream, map[string]string{
		"signalId":         "query:req-private",
		"signalType":       "query",
		"searchRequestId":  "req-private",
		"userId":           "user-private",
		"normalizedQuery":  "身份证号 123456",
		"relatedTerms":     `not-json`,
		"engagedObjectIds": `[]`,
		"resultCount":      "1",
		"createdAt":        time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("XAdd: %v", err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 {
		t.Fatalf("malformed signal must be quarantined: processed=%d err=%v", processed, err)
	}
	if err := redis.XGroupCreateMkStream(
		ctx,
		SearchRecommendationSignalDLQ,
		"dlq-audit",
		"0",
	); err != nil {
		t.Fatalf("create DLQ audit group: %v", err)
	}
	dlq, err := redis.XReadGroup(
		ctx,
		"dlq-audit",
		"auditor",
		map[string]string{SearchRecommendationSignalDLQ: ">"},
		10,
		0,
	)
	if err != nil || len(dlq) != 1 {
		t.Fatalf("read sanitized DLQ: count=%d err=%v", len(dlq), err)
	}
	for _, value := range dlq[0].Values {
		if value == "身份证号 123456" || value == "user-private" {
			t.Fatalf("DLQ leaked raw private payload: %#v", dlq[0].Values)
		}
	}
	pending, err := redis.XPendingCount(
		ctx,
		SearchRecommendationSignalStream,
		SearchSignalConsumerGroup,
	)
	if err != nil || pending != 0 {
		t.Fatalf("malformed source must be acked: pending=%d err=%v", pending, err)
	}
}

func TestSearchSignalConsumerLeavesTransientProjectionFailurePending(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	projector := &recordingSearchProjector{err: errors.New("mongo unavailable")}
	consumer := NewSearchSignalConsumer(redis, projector, "worker-transient", nil)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, SearchRecommendationSignalStream, map[string]string{
		"signalId":         "query:req-retry",
		"signalType":       "query",
		"searchRequestId":  "req-retry",
		"userId":           "user-1",
		"normalizedQuery":  "成都",
		"relatedTerms":     `[]`,
		"engagedObjectIds": `[]`,
		"resultCount":      "1",
		"createdAt":        time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("XAdd: %v", err)
	}
	if _, err := consumer.ProcessOnce(ctx); err == nil {
		t.Fatal("transient projection failure must propagate")
	}
	pending, err := redis.XPendingCount(
		ctx,
		SearchRecommendationSignalStream,
		SearchSignalConsumerGroup,
	)
	if err != nil || pending != 1 {
		t.Fatalf("transient source must remain pending: pending=%d err=%v", pending, err)
	}
}

func TestSearchSignalConsumerNeverAcksUncompletedLeaseAfterReleaseFailure(t *testing.T) {
	ctx := context.Background()
	memory := rtredis.NewMemoryClient()
	redis := &deleteFailingRedis{
		Client: memory,
		err:    errors.New("redis delete unavailable"),
	}
	projector := &recordingSearchProjector{err: errors.New("mongo unavailable")}
	consumer := NewSearchSignalConsumer(redis, projector, "worker-release-failure", nil)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, SearchRecommendationSignalStream, map[string]string{
		"signalId":         "query:req-release-failure",
		"signalType":       "query",
		"searchRequestId":  "req-release-failure",
		"userId":           "user-1",
		"normalizedQuery":  "成都",
		"relatedTerms":     `[]`,
		"engagedObjectIds": `[]`,
		"resultCount":      "1",
		"createdAt":        time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("XAdd: %v", err)
	}
	if _, err := consumer.ProcessOnce(ctx); err == nil {
		t.Fatal("transient projection failure must propagate")
	}

	projector.err = nil
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("processing lease must remain retryable: %v", err)
	}
	if processed != 0 {
		t.Fatalf("uncompleted processing lease must not be acked: processed=%d", processed)
	}
	pending, err := memory.XPendingCount(
		ctx,
		SearchRecommendationSignalStream,
		SearchSignalConsumerGroup,
	)
	if err != nil || pending != 1 {
		t.Fatalf("uncompleted source must remain pending: pending=%d err=%v", pending, err)
	}
}

type recordingSearchProjector struct {
	events []ProjectorEvent
	err    error
}

func (r *recordingSearchProjector) Project(_ context.Context, event ProjectorEvent) error {
	r.events = append(r.events, event)
	return r.err
}

type deleteFailingRedis struct {
	rtredis.Client
	err error
}

func (f *deleteFailingRedis) Del(context.Context, ...string) error {
	return f.err
}
