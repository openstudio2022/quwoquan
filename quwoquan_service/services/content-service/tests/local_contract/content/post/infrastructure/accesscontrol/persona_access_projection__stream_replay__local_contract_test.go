package accesscontrol_test

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/accesscontrol"
)

func TestPersonaAccessProjectionPersistsOnlyBlockState(t *testing.T) {
	writer := newRecordingPersonaAccessWriter()
	projector := NewPersonaAccessProjectionWithWriter(writer)
	now := time.Date(2026, 7, 14, 9, 0, 0, 0, time.UTC)

	if err := projector.Apply(context.Background(), personaAccessTestEvent(
		"evt-follow", PersonaFollowStateChanged, "viewer", "target", true, 2, now,
	)); err != nil {
		t.Fatalf("consume follow event: %v", err)
	}
	if len(writer.blocked) != 0 {
		t.Fatalf("Content must not copy follow state into access projection: %+v", writer.blocked)
	}

	block := personaAccessTestEvent("evt-block", PersonaBlocked, "viewer", "target", false, 4, now.Add(time.Second))
	if err := projector.Apply(context.Background(), block); err != nil {
		t.Fatalf("project block: %v", err)
	}
	if !writer.blocked["viewer|target"] {
		t.Fatal("block did not project directional access marker")
	}

	// Older access events cannot overwrite a newer marker.
	stale := personaAccessTestEvent("evt-stale-unblock", PersonaUnblocked, "viewer", "target", false, 3, now.Add(2*time.Second))
	if err := projector.Apply(context.Background(), stale); err != nil {
		t.Fatalf("project stale unblock: %v", err)
	}
	if !writer.blocked["viewer|target"] {
		t.Fatal("stale unblock overwrote newer block marker")
	}

	unblock := personaAccessTestEvent("evt-unblock", PersonaUnblocked, "viewer", "target", false, 5, now.Add(3*time.Second))
	if err := projector.Apply(context.Background(), unblock); err != nil {
		t.Fatalf("project unblock: %v", err)
	}
	if writer.blocked["viewer|target"] {
		t.Fatal("unblock did not clear access marker")
	}
	if len(writer.events) != 4 {
		t.Fatalf("ordered inbox events=%d want 4", len(writer.events))
	}
}

func TestPersonaAccessProjectionConsumerReplaysAndAcknowledges(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	writer := newRecordingPersonaAccessWriter()
	consumer := NewPersonaAccessProjectionConsumer(redis, NewPersonaAccessProjectionWithWriter(writer), "worker-1", nil)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("ensure group: %v", err)
	}
	event := personaAccessTestEvent("evt-stream", PersonaBlocked, "viewer", "target", false, 1, time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC))
	if _, err := redis.XAdd(ctx, PersonaRelationshipEventStream, personaAccessStreamValues(event)); err != nil {
		t.Fatalf("append stream event: %v", err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("consume stream event: %v", err)
	}
	if processed != 1 || !writer.blocked["viewer|target"] {
		t.Fatalf("processed=%d blocked=%v", processed, writer.blocked)
	}
	pending, err := redis.XReadGroup(ctx, PersonaAccessProjectionConsumerGroup, "worker-1", map[string]string{PersonaRelationshipEventStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("read pending: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d want 0", len(pending))
	}
}

func TestPersonaAccessProjectionConsumerDeadLettersInvalidEvent(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	consumer := NewPersonaAccessProjectionConsumer(redis, NewPersonaAccessProjectionWithWriter(newRecordingPersonaAccessWriter()), "worker-1", nil)
	if _, err := redis.XAdd(ctx, PersonaRelationshipEventStream, map[string]string{
		"eventId": "evt-invalid", "eventName": string(PersonaBlocked), "pairId": "pair", "sourcePersonaId": "viewer", "targetPersonaId": "target",
		"following": "false", "version": "not-a-number", "occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("append invalid stream event: %v", err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 {
		t.Fatalf("consume invalid event processed=%d err=%v", processed, err)
	}
	if err := redis.XGroupCreateMkStream(ctx, PersonaAccessProjectionDLQ, "inspection", "0"); err != nil {
		t.Fatalf("ensure dlq inspection group: %v", err)
	}
	dlq, err := redis.XReadGroup(ctx, "inspection", "test", map[string]string{PersonaAccessProjectionDLQ: ">"}, 10, 0)
	if err != nil {
		t.Fatalf("read dlq: %v", err)
	}
	if len(dlq) != 1 || dlq[0].Values["eventId"] != "evt-invalid" {
		t.Fatalf("dlq=%+v want evt-invalid", dlq)
	}
}

func personaAccessTestEvent(eventID string, name PersonaRelationshipEventName, source, target string, following bool, version int64, occurredAt time.Time) PersonaRelationshipEvent {
	return PersonaRelationshipEvent{
		EventID: eventID, EventName: name, PairID: "pair-" + source + "-" + target,
		SourcePersonaID: source, TargetPersonaID: target, Following: following,
		Version: version, OccurredAt: occurredAt,
	}
}

func personaAccessStreamValues(event PersonaRelationshipEvent) map[string]string {
	return map[string]string{
		"eventId": event.EventID, "eventName": string(event.EventName), "pairId": event.PairID,
		"sourcePersonaId": event.SourcePersonaID, "targetPersonaId": event.TargetPersonaID,
		"following": "false", "version": "1", "occurredAt": event.OccurredAt.Format(time.RFC3339Nano),
	}
}

type recordingPersonaAccessWriter struct {
	blocked map[string]bool
	version map[string]int64
	events  map[string]struct{}
}

func newRecordingPersonaAccessWriter() *recordingPersonaAccessWriter {
	return &recordingPersonaAccessWriter{blocked: map[string]bool{}, version: map[string]int64{}, events: map[string]struct{}{}}
}

func (w *recordingPersonaAccessWriter) ApplyBlocked(_ context.Context, event PersonaRelationshipEvent) error {
	return w.apply(event, true)
}

func (w *recordingPersonaAccessWriter) ApplyUnblocked(_ context.Context, event PersonaRelationshipEvent) error {
	return w.apply(event, false)
}

func (w *recordingPersonaAccessWriter) apply(event PersonaRelationshipEvent, blocked bool) error {
	key := event.SourcePersonaID + "|" + event.TargetPersonaID
	if w.version[key] >= event.Version {
		return nil
	}
	w.version[key] = event.Version
	w.blocked[key] = blocked
	return nil
}

func (w *recordingPersonaAccessWriter) RecordAppliedEvent(_ context.Context, event PersonaRelationshipEvent) (bool, error) {
	if _, exists := w.events[event.EventID]; exists {
		return false, nil
	}
	w.events[event.EventID] = struct{}{}
	return true, nil
}
