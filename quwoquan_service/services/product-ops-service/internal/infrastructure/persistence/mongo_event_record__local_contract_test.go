package persistence

import (
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
)

func TestMongoEventRecordUsesThirtyDayRetentionForLoginDetails(t *testing.T) {
	const occurredAt = "2026-07-14T08:00:00Z"
	record, _, err := newMongoEventRecord(application.EventRecordInput{
		EventID:    "login-retention-contract",
		EventType:  "journey_action",
		EventName:  "login_success",
		OccurredAt: occurredAt,
	})
	if err != nil {
		t.Fatalf("new login event record: %v", err)
	}
	want := time.Date(2026, 8, 13, 8, 0, 0, 0, time.UTC)
	if !record.ExpiresAt.Equal(want) {
		t.Fatalf("login detail retention must be 30 days: got=%s want=%s", record.ExpiresAt, want)
	}
}

func TestMongoEventRecordKeepsDefaultNinetyDayRetention(t *testing.T) {
	const occurredAt = "2026-07-14T08:00:00Z"
	record, _, err := newMongoEventRecord(application.EventRecordInput{
		EventID:    "page-retention-contract",
		EventType:  "experience",
		EventName:  "page_open",
		OccurredAt: occurredAt,
	})
	if err != nil {
		t.Fatalf("new page event record: %v", err)
	}
	want := time.Date(2026, 10, 12, 8, 0, 0, 0, time.UTC)
	if !record.ExpiresAt.Equal(want) {
		t.Fatalf("default event retention must remain 90 days: got=%s want=%s", record.ExpiresAt, want)
	}
}
