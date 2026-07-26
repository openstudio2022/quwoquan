package recommendation_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

func TestPersonaRelationshipProjectionPreservesOrderingAndBlockSemantics(t *testing.T) {
	writer := newRecordingRelationshipProjectionWriter()
	projector := NewPersonaRelationshipProjectionWithWriter(writer)
	now := time.Date(2026, 7, 14, 9, 0, 0, 0, time.UTC)

	follow := relationshipProjectionTestEvent("evt-follow", PersonaFollowStateChanged, "viewer", "target", true, 2, now)
	if err := projector.Apply(context.Background(), follow); err != nil {
		t.Fatalf("project follow: %v", err)
	}
	stale := relationshipProjectionTestEvent("evt-stale", PersonaFollowStateChanged, "viewer", "target", false, 1, now.Add(time.Second))
	if err := projector.Apply(context.Background(), stale); err != nil {
		t.Fatalf("project stale follow: %v", err)
	}
	if got := writer.direction("viewer", "target"); !got.following || got.version != 2 {
		t.Fatalf("stale event overwrote newer relation: %+v", got)
	}

	mutual := relationshipProjectionTestEvent("evt-mutual", PersonaFollowStateChanged, "target", "viewer", true, 3, now.Add(2*time.Second))
	if err := projector.Apply(context.Background(), mutual); err != nil {
		t.Fatalf("project reciprocal follow: %v", err)
	}
	block := relationshipProjectionTestEvent("evt-block", PersonaBlocked, "viewer", "target", false, 4, now.Add(3*time.Second))
	if err := projector.Apply(context.Background(), block); err != nil {
		t.Fatalf("project block: %v", err)
	}
	if got := writer.direction("viewer", "target"); got.following || got.version != 4 {
		t.Fatalf("block did not clear source direction: %+v", got)
	}
	if got := writer.direction("target", "viewer"); got.following || got.version != 4 {
		t.Fatalf("block did not clear reciprocal direction: %+v", got)
	}
	if !writer.blocked["viewer|target"] {
		t.Fatalf("block did not project directional block marker")
	}

	unblock := relationshipProjectionTestEvent("evt-unblock", PersonaUnblocked, "viewer", "target", false, 5, now.Add(4*time.Second))
	if err := projector.Apply(context.Background(), unblock); err != nil {
		t.Fatalf("project unblock: %v", err)
	}
	if writer.blocked["viewer|target"] {
		t.Fatalf("unblock did not clear block marker")
	}
	if got := writer.direction("viewer", "target"); got.following {
		t.Fatalf("unblock must not restore prior follow: %+v", got)
	}
}

func TestPersonaRelationshipProjectionConsumerReplaysAndAcknowledges(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	writer := newRecordingRelationshipProjectionWriter()
	consumer := NewPersonaRelationshipProjectionConsumer(redis, NewPersonaRelationshipProjectionWithWriter(writer), "worker-1", nil)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("ensure group: %v", err)
	}
	now := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	if _, err := redis.XAdd(ctx, PersonaRelationshipEventStream, relationshipProjectionStreamValues(
		relationshipProjectionTestEvent("evt-stream", PersonaFollowStateChanged, "viewer", "target", true, 1, now),
	)); err != nil {
		t.Fatalf("append stream event: %v", err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("consume stream event: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d want 1", processed)
	}
	if got := writer.direction("viewer", "target"); !got.following || got.version != 1 {
		t.Fatalf("projection=%+v want following version 1", got)
	}
	pending, err := redis.XReadGroup(ctx, PersonaRelationshipProjectionConsumerGroup, "worker-1", map[string]string{PersonaRelationshipEventStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("read pending: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d want 0", len(pending))
	}
}

func TestPersonaRelationshipProjectionConsumerDeadLettersInvalidEvent(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	consumer := NewPersonaRelationshipProjectionConsumer(redis, NewPersonaRelationshipProjectionWithWriter(newRecordingRelationshipProjectionWriter()), "worker-1", nil)
	if _, err := redis.XAdd(ctx, PersonaRelationshipEventStream, map[string]string{
		"eventId": "evt-invalid", "eventName": string(PersonaFollowStateChanged), "pairId": "pair", "sourcePersonaId": "viewer", "targetPersonaId": "target",
		"following": "true", "version": "not-a-number", "occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("append invalid stream event: %v", err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("consume invalid stream event: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d want 1", processed)
	}
	if err := redis.XGroupCreateMkStream(ctx, PersonaRelationshipProjectionDLQ, "inspection", "0"); err != nil {
		t.Fatalf("ensure dlq inspection group: %v", err)
	}
	dlq, err := redis.XReadGroup(ctx, "inspection", "test", map[string]string{PersonaRelationshipProjectionDLQ: ">"}, 10, 0)
	if err != nil {
		t.Fatalf("read dlq: %v", err)
	}
	if len(dlq) != 1 || dlq[0].Values["eventId"] != "evt-invalid" {
		t.Fatalf("dlq=%+v want evt-invalid", dlq)
	}
}

func relationshipProjectionTestEvent(eventID string, name PersonaRelationshipEventName, source, target string, following bool, version int64, occurredAt time.Time) PersonaRelationshipProjectionEvent {
	return PersonaRelationshipProjectionEvent{
		EventID: eventID, EventName: name, PairID: "pair-" + source + "-" + target,
		SourcePersonaID: source, TargetPersonaID: target, Following: following,
		Version: version, OccurredAt: occurredAt,
	}
}

func relationshipProjectionStreamValues(event PersonaRelationshipProjectionEvent) map[string]string {
	return map[string]string{
		"eventId": event.EventID, "eventName": string(event.EventName), "pairId": event.PairID,
		"sourcePersonaId": event.SourcePersonaID, "targetPersonaId": event.TargetPersonaID,
		"following": "true", "version": "1", "occurredAt": event.OccurredAt.Format(time.RFC3339Nano),
	}
}

type relationshipProjectionDirection struct {
	following bool
	version   int64
}

type recordingRelationshipProjectionWriter struct {
	directions map[string]relationshipProjectionDirection
	blocked    map[string]bool
	events     map[string]struct{}
}

func newRecordingRelationshipProjectionWriter() *recordingRelationshipProjectionWriter {
	return &recordingRelationshipProjectionWriter{
		directions: map[string]relationshipProjectionDirection{},
		blocked:    map[string]bool{},
		events:     map[string]struct{}{},
	}
}

func (w *recordingRelationshipProjectionWriter) ApplyFollowState(_ context.Context, event PersonaRelationshipProjectionEvent) error {
	key := event.SourcePersonaID + "|" + event.TargetPersonaID
	if current, ok := w.directions[key]; ok && current.version >= event.Version {
		return nil
	}
	w.directions[key] = relationshipProjectionDirection{following: event.Following, version: event.Version}
	return nil
}

func (w *recordingRelationshipProjectionWriter) ApplyBlocked(ctx context.Context, event PersonaRelationshipProjectionEvent) error {
	if err := w.ApplyFollowState(ctx, PersonaRelationshipProjectionEvent{
		SourcePersonaID: event.SourcePersonaID, TargetPersonaID: event.TargetPersonaID, Following: false, Version: event.Version,
	}); err != nil {
		return err
	}
	if err := w.ApplyFollowState(ctx, PersonaRelationshipProjectionEvent{
		SourcePersonaID: event.TargetPersonaID, TargetPersonaID: event.SourcePersonaID, Following: false, Version: event.Version,
	}); err != nil {
		return err
	}
	w.blocked[event.SourcePersonaID+"|"+event.TargetPersonaID] = true
	return nil
}

func (w *recordingRelationshipProjectionWriter) ApplyUnblocked(_ context.Context, event PersonaRelationshipProjectionEvent) error {
	w.blocked[event.SourcePersonaID+"|"+event.TargetPersonaID] = false
	return nil
}

func (w *recordingRelationshipProjectionWriter) RecordAppliedEvent(_ context.Context, event PersonaRelationshipProjectionEvent) (bool, error) {
	if _, exists := w.events[event.EventID]; exists {
		return false, nil
	}
	w.events[event.EventID] = struct{}{}
	return true, nil
}

func (w *recordingRelationshipProjectionWriter) direction(source, target string) relationshipProjectionDirection {
	return w.directions[source+"|"+target]
}
