package recommendation_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestPremiumPoolProjectorProjectsOpsEventsFailClosed(t *testing.T) {
	writer := &fakePremiumPoolProjectionWriter{}
	projector := NewPremiumPoolProjectorWithWriter(writer)
	now := time.Date(2026, 6, 25, 12, 0, 0, 0, time.UTC)
	projector.SetNow(func() time.Time { return now })

	payload := map[string]any{
		"contentId":        "post_premium_1",
		"scope":            "global",
		"status":           "active",
		"qualityAdmission": "approved",
		"qualityScore":     0.92,
		"supplySource":     "data_engineering",
		"sourceTaskId":     "task_1",
		"auditId":          "audit_1",
		"rollbackToken":    "rbk_1",
		"featuredAt":       now.Add(-time.Hour).Format(time.RFC3339),
		"expiresAt":        now.Add(time.Hour).Format(time.RFC3339),
		"updatedAt":        now.Format(time.RFC3339),
	}
	if err := projector.Project(context.Background(), ProjectorEvent{Type: PremiumPoolEntryUpsertedEvent, Payload: payload, OccurredAt: now}); err != nil {
		t.Fatalf("project upsert: %v", err)
	}
	if got := writer.upserts[0]["eligibilityState"]; got != "eligible" {
		t.Fatalf("upsert eligibility=%v want eligible", got)
	}
	if got := writer.upserts[0]["sourceTaskId"]; got != "task_1" {
		t.Fatalf("sourceTaskId=%v want task_1", got)
	}

	payload["status"] = "rolled_back"
	if err := projector.Project(context.Background(), ProjectorEvent{Type: PremiumPoolEntryRolledBackEvent, Payload: payload, OccurredAt: now}); err != nil {
		t.Fatalf("project rollback: %v", err)
	}
	if got := writer.upserts[1]["eligibilityState"]; got != "ineligible" {
		t.Fatalf("rollback eligibility=%v want ineligible", got)
	}
	if reasons := writer.upserts[1]["ineligibleReasons"].([]string); !containsString(reasons, "inactive_status") {
		t.Fatalf("rollback reasons=%v must include inactive_status", reasons)
	}

	payload["status"] = "takedown_ejected"
	payload["takedownEjected"] = true
	if err := projector.Project(context.Background(), ProjectorEvent{Type: PremiumPoolEntryTakedownEjectedEvent, Payload: payload, OccurredAt: now}); err != nil {
		t.Fatalf("project takedown: %v", err)
	}
	if reasons := writer.upserts[2]["ineligibleReasons"].([]string); !containsString(reasons, "takedown_ejected") {
		t.Fatalf("takedown reasons=%v must include takedown_ejected", reasons)
	}
}

func TestPremiumPoolProjectorMarksContentTakedown(t *testing.T) {
	writer := &fakePremiumPoolProjectionWriter{}
	projector := NewPremiumPoolProjectorWithWriter(writer)
	now := time.Date(2026, 6, 25, 12, 0, 0, 0, time.UTC)
	projector.SetNow(func() time.Time { return now })

	if err := projector.Project(context.Background(), ProjectorEvent{
		Type:        "PostDeleted",
		AggregateID: "post_premium_1",
		Payload:     map[string]any{"postId": "post_premium_1"},
		OccurredAt:  now,
	}); err != nil {
		t.Fatalf("project post delete: %v", err)
	}
	if len(writer.takedowns) != 1 || writer.takedowns[0] != "post_premium_1" {
		t.Fatalf("takedowns=%v want post_premium_1", writer.takedowns)
	}
}

func TestPremiumPoolEventConsumerProcessesOpsEnvelope(t *testing.T) {
	writer := &fakePremiumPoolProjectionWriter{}
	projector := NewPremiumPoolProjectorWithWriter(writer)
	now := time.Date(2026, 6, 25, 12, 0, 0, 0, time.UTC)
	projector.SetNow(func() time.Time { return now })
	consumer := NewPremiumPoolEventConsumer(nil, projector, nil)

	raw := `{"payload":{"type":"PremiumPoolEntryUpserted","aggregateType":"PremiumPoolEntry","aggregateId":"post_premium_1","data":{"contentId":"post_premium_1","scope":"global","status":"active","qualityAdmission":"approved","qualityScore":0.93,"auditId":"audit_1","expiresAt":"2026-06-25T13:00:00Z"},"occurredAt":"2026-06-25T12:00:00Z"}}`
	if err := consumer.ProcessMessage(context.Background(), PremiumPoolEntryUpsertedChannel, raw); err != nil {
		t.Fatalf("process envelope: %v", err)
	}
	if len(writer.upserts) != 1 {
		t.Fatalf("upserts=%d want 1", len(writer.upserts))
	}
	if got := writer.upserts[0]["contentId"]; got != "post_premium_1" {
		t.Fatalf("contentId=%v want post_premium_1", got)
	}
}

type fakePremiumPoolProjectionWriter struct {
	upserts   []bson.M
	takedowns []string
}

func (w *fakePremiumPoolProjectionWriter) UpsertPremiumProjection(_ context.Context, fields bson.M) error {
	copied := bson.M{}
	for key, value := range fields {
		copied[key] = value
	}
	w.upserts = append(w.upserts, copied)
	return nil
}

func (w *fakePremiumPoolProjectionWriter) MarkPremiumProjectionTakedown(_ context.Context, contentID string, _ time.Time) error {
	w.takedowns = append(w.takedowns, contentID)
	return nil
}
