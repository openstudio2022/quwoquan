package infrastructure_test

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmessaging "quwoquan_service/services/content-service/internal/content/comment/infrastructure/messaging"
)

func TestCommentViewerRelationshipConsumerUsesObjectLocalGroupAndDLQ(
	t *testing.T,
) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	projector := &recordingViewerRelationshipProjector{}
	consumer := commentmessaging.NewViewerRelationshipConsumer(
		redis,
		projector,
		"comment-test-worker",
		nil,
	)
	if _, err := redis.XAdd(ctx, commentmessaging.ViewerRelationshipEventStream, map[string]string{
		"eventId": "valid", "eventName": "PersonaFollowStateChanged",
		"pairId": "pair", "sourcePersonaId": "viewer",
		"targetPersonaId": "author", "following": "true", "version": "1",
		"occurredAt": time.Date(2026, 8, 2, 11, 0, 0, 0, time.UTC).
			Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("append valid relationship event: %v", err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 || len(projector.events) != 1 {
		t.Fatalf("consume valid event: processed=%d events=%d err=%v", processed, len(projector.events), err)
	}
	if projector.events[0].EventID != "valid" || !projector.events[0].Following {
		t.Fatalf("unexpected typed event: %+v", projector.events[0])
	}
	pending, err := redis.XReadGroup(
		ctx,
		commentmessaging.ViewerRelationshipConsumerGroup,
		"comment-test-worker",
		map[string]string{commentmessaging.ViewerRelationshipEventStream: "0"},
		10,
		0,
	)
	if err != nil || len(pending) != 0 {
		t.Fatalf("valid event was not acknowledged: pending=%d err=%v", len(pending), err)
	}

	if _, err := redis.XAdd(ctx, commentmessaging.ViewerRelationshipEventStream, map[string]string{
		"eventId": "invalid", "eventName": "PersonaFollowStateChanged",
		"pairId": "pair", "sourcePersonaId": "viewer",
		"targetPersonaId": "author", "following": "true", "version": "broken",
		"occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("append invalid relationship event: %v", err)
	}
	processed, err = consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 {
		t.Fatalf("consume invalid event: processed=%d err=%v", processed, err)
	}
	if err := redis.XGroupCreateMkStream(
		ctx,
		commentmessaging.ViewerRelationshipDLQ,
		"inspection",
		"0",
	); err != nil {
		t.Fatalf("create DLQ inspection group: %v", err)
	}
	dlq, err := redis.XReadGroup(
		ctx,
		"inspection",
		"inspector",
		map[string]string{commentmessaging.ViewerRelationshipDLQ: ">"},
		10,
		0,
	)
	if err != nil || len(dlq) != 1 || dlq[0].Values["eventId"] != "invalid" {
		t.Fatalf("invalid event DLQ mismatch: dlq=%+v err=%v", dlq, err)
	}
}

type recordingViewerRelationshipProjector struct {
	events []commentapp.ViewerRelationshipEvent
}

func (projector *recordingViewerRelationshipProjector) Apply(
	_ context.Context,
	event commentapp.ViewerRelationshipEvent,
) error {
	projector.events = append(projector.events, event)
	return nil
}
