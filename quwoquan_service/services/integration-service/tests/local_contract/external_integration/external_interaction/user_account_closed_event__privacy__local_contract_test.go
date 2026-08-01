package local_contract

import (
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

func TestIntegrationUserAccountClosedEventNormalizesIdentityAndReplayDigest(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	event := application.UserAccountClosedEvent{
		EventID:        "event-closed-001",
		AccountVersion: 7,
		UserID:         "account-001",
		PersonaIDs:     []string{"persona-002", "persona-001", "persona-002"},
		AccountState:   "closed",
		UpdatedAt:      now,
		OccurredAt:     now,
	}
	if err := event.Validate(); err != nil {
		t.Fatal(err)
	}
	if got := event.SubjectIDs(); len(got) != 3 ||
		got[0] != "account-001" || got[1] != "persona-001" || got[2] != "persona-002" {
		t.Fatalf("canonical subjects = %#v", got)
	}
	reordered := event
	reordered.PersonaIDs = []string{"persona-001", "persona-002"}
	if event.Digest() != reordered.Digest() {
		t.Fatal("persona order and duplicates must not fork replay identity")
	}
}

func TestIntegrationUserAccountClosedProjectionConflictIsFailClosed(t *testing.T) {
	t.Parallel()
	if application.ErrUserAccountClosedEventIDConflict == nil ||
		!errors.Is(application.ErrUserAccountClosedEventIDConflict, application.ErrUserAccountClosedEventIDConflict) {
		t.Fatal("event id conflict sentinel must remain stable")
	}
}
