// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: append-external-interaction-attempt-local
package external_interaction_attempt_fact_test

import (
	"context"
	"strings"
	"testing"
	"time"

	attemptapp "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/application"
	attemptdomain "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/domain"
)

func TestAttemptFactCanonicalizesAndRejectsMutableOrInvalidInput(t *testing.T) {
	t.Parallel()
	createdAt := time.Date(2026, time.August, 4, 9, 30, 0, 0, time.FixedZone("CST", 8*60*60))
	fact, err := attemptdomain.NewFact(attemptdomain.Fact{
		AttemptID:             " attempt-001 ",
		RequestID:             " request-001 ",
		TaskID:                " task-001 ",
		Operation:             " push ",
		Provider:              " fcm ",
		ProviderRequestDigest: "sha256:" + strings.Repeat("a", 64),
		LatencyMS:             12,
		Status:                " sent_unconfirmed ",
		RecoveryAction:        " none ",
		CreatedAt:             createdAt,
	})
	if err != nil {
		t.Fatal(err)
	}
	if fact.AttemptID != "attempt-001" || fact.RequestID != "request-001" || fact.TaskID != "task-001" {
		t.Fatalf("canonical identity = %#v", fact)
	}
	if fact.Operation != "push" || fact.Provider != "fcm" || fact.Status != "sent_unconfirmed" {
		t.Fatalf("canonical provider attempt = %#v", fact)
	}
	if fact.CreatedAt.Location() != time.UTC || !fact.CreatedAt.Equal(createdAt) {
		t.Fatalf("createdAt = %s, want the same instant in UTC", fact.CreatedAt)
	}
	if fact.Attributes == nil {
		t.Fatal("attributes must canonicalize to an owned empty map")
	}

	invalid := fact
	invalid.ProviderRequestDigest = "sha256:not-a-digest"
	if _, err := attemptdomain.NewFact(invalid); err == nil {
		t.Fatal("non-canonical provider request digest must fail closed")
	}
	invalid = fact
	invalid.LatencyMS = -1
	if _, err := attemptdomain.NewFact(invalid); err == nil {
		t.Fatal("negative provider latency must fail closed")
	}
}

func TestAttemptAppenderOwnsValidationAndAppendOnlyPort(t *testing.T) {
	t.Parallel()
	store := &attemptRecordingStore{}
	appender := attemptapp.NewAppender(store)
	fact := attemptdomain.Fact{
		AttemptID:             "attempt-002",
		RequestID:             "request-002",
		TaskID:                "task-002",
		Operation:             "push",
		Provider:              "apns",
		ProviderRequestDigest: "sha256:" + strings.Repeat("b", 64),
		Status:                "failed",
		RecoveryAction:        "manual_recover",
		CreatedAt:             time.Now().UTC(),
	}
	appended, err := appender.Append(context.Background(), fact)
	if err != nil || !appended {
		t.Fatalf("append result appended=%v err=%v", appended, err)
	}
	if len(store.facts) != 1 || store.facts[0].AttemptID != fact.AttemptID {
		t.Fatalf("recorded facts = %#v", store.facts)
	}
	if _, err := attemptapp.NewAppender(nil).Append(context.Background(), fact); err == nil {
		t.Fatal("missing append store must fail closed")
	}
}

type attemptRecordingStore struct {
	facts []attemptdomain.Fact
}

func (s *attemptRecordingStore) AppendIfAbsent(_ context.Context, fact attemptdomain.Fact) (bool, error) {
	s.facts = append(s.facts, fact)
	return true, nil
}
