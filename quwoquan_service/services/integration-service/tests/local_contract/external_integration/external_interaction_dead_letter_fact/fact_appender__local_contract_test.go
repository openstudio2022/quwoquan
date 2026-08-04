// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
package local_contract

import (
	"context"
	"testing"
	"time"

	deadletterapp "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/application"
	deadletterdomain "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/domain"
)

func TestDeadLetterFactCanonicalizesImmutableTerminalIdentity(t *testing.T) {
	t.Parallel()
	createdAt := time.Date(2026, time.August, 4, 10, 15, 0, 0, time.FixedZone("CST", 8*60*60))
	fact, err := deadletterdomain.NewFact(deadletterdomain.Fact{
		DeadLetterID:   " dead-letter-001 ",
		TaskID:         " task-001 ",
		RequestID:      " request-001 ",
		Operation:      " push ",
		Provider:       " fcm ",
		FinalError:     " provider rejected request ",
		RecoveryAction: " manual_recover ",
		CreatedAt:      createdAt,
	})
	if err != nil {
		t.Fatal(err)
	}
	if fact.DeadLetterID != "dead-letter-001" || fact.TaskID != "task-001" || fact.RequestID != "request-001" {
		t.Fatalf("canonical dead-letter identity = %#v", fact)
	}
	if fact.Operation != "push" || fact.Provider != "fcm" || fact.FinalError != "provider rejected request" {
		t.Fatalf("canonical terminal fact = %#v", fact)
	}
	if fact.CreatedAt.Location() != time.UTC || !fact.CreatedAt.Equal(createdAt) {
		t.Fatalf("createdAt = %s, want the same instant in UTC", fact.CreatedAt)
	}

	invalid := fact
	invalid.FinalError = ""
	if _, err := deadletterdomain.NewFact(invalid); err == nil {
		t.Fatal("dead-letter fact without a terminal error must fail closed")
	}
}

func TestDeadLetterAppenderKeepsOneImmutableFactPerIdentity(t *testing.T) {
	t.Parallel()
	repository := &deadLetterRecordingRepository{facts: map[string]deadletterdomain.Fact{}}
	appender := deadletterapp.NewAppender(repository)
	fact := deadletterdomain.Fact{
		DeadLetterID:   "dead-letter-002",
		TaskID:         "task-002",
		RequestID:      "request-002",
		Operation:      "push",
		Provider:       "apns",
		FinalError:     "provider rejected request",
		RecoveryAction: "manual_recover",
		CreatedAt:      time.Now().UTC(),
	}
	for attempt, wantAppended := range []bool{true, false} {
		appended, err := appender.Append(context.Background(), fact)
		if err != nil || appended != wantAppended {
			t.Fatalf("attempt=%d appended=%v err=%v, want appended=%v", attempt, appended, err, wantAppended)
		}
	}
	facts, err := appender.ListByRequest(context.Background(), fact.RequestID)
	if err != nil || len(facts) != 1 || facts[0] != fact {
		t.Fatalf("immutable facts = %#v err=%v", facts, err)
	}
	if _, err := deadletterapp.NewAppender(nil).Append(context.Background(), fact); err == nil {
		t.Fatal("missing dead-letter repository must fail closed")
	}
}

type deadLetterRecordingRepository struct {
	facts map[string]deadletterdomain.Fact
}

func (r *deadLetterRecordingRepository) AppendIfAbsent(_ context.Context, fact deadletterdomain.Fact) (bool, error) {
	if _, exists := r.facts[fact.DeadLetterID]; exists {
		return false, nil
	}
	r.facts[fact.DeadLetterID] = fact
	return true, nil
}

func (r *deadLetterRecordingRepository) ListByRequest(_ context.Context, requestID string) ([]deadletterdomain.Fact, error) {
	result := make([]deadletterdomain.Fact, 0, len(r.facts))
	for _, fact := range r.facts {
		if fact.RequestID == requestID {
			result = append(result, fact)
		}
	}
	return result, nil
}
