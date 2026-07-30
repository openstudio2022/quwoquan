// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package api_integration

import (
	"errors"
	"testing"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	"quwoquan_service/services/search-service/internal/search/search_query/application"
	accountclosure "quwoquan_service/services/search-service/internal/search/search_query/infrastructure/accountclosure"
)

func TestUserAccountRestrictionProjectionIsReversibleMonotonicAndReplaySafe(
	t *testing.T,
) {
	cleanSearchCollections(t)
	ctx := t.Context()
	projection, err := accountclosure.NewMongoAccountRestrictionProjection(mongoDB)
	if err != nil {
		t.Fatal(err)
	}
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	occurredAt := time.Date(2026, time.July, 28, 12, 0, 0, 0, time.UTC)
	suspended := accountrestriction.Event{
		EventID:        "event-suspend-7",
		EventName:      accountrestriction.UserSuspendedEventName,
		AccountID:      "account-restricted",
		AccountVersion: 7,
		UserID:         "account-restricted",
		PersonaIDs:     []string{"persona-restricted"},
		AccountState:   "suspended",
		AuthEpoch:      7,
		DecisionRef:    "decision-suspend-7",
		OccurredAt:     occurredAt,
	}
	result, err := projection.Apply(ctx, suspended)
	if err != nil || result.Replayed || result.Affected != 0 {
		t.Fatalf("suspend result=%+v err=%v", result, err)
	}
	restricted, err := projection.RestrictedSubjects(
		ctx,
		[]string{"persona-restricted", "persona-active"},
	)
	if err != nil || !restricted["persona-restricted"] || restricted["persona-active"] {
		t.Fatalf("restriction read=%v err=%v", restricted, err)
	}

	replay, err := projection.Apply(ctx, suspended)
	if err != nil || !replay.Replayed || replay.Affected != 0 {
		t.Fatalf("replay=%+v err=%v", replay, err)
	}
	conflict := suspended
	conflict.DecisionRef = "different-decision"
	if _, err := projection.Apply(ctx, conflict); !errors.Is(
		err,
		application.ErrUserAccountRestrictionProjectionConflict,
	) {
		t.Fatalf("eventId conflict err=%v", err)
	}

	restored := suspended
	restored.EventID = "event-restore-8"
	restored.EventName = accountrestriction.UserRestoredEventName
	restored.AccountVersion = 8
	restored.AccountState = "active"
	restored.AuthEpoch = 8
	restored.DecisionRef = "decision-restore-8"
	restored.OccurredAt = occurredAt.Add(time.Minute)
	result, err = projection.Apply(ctx, restored)
	if err != nil || result.Replayed || result.Affected != 0 {
		t.Fatalf("restore result=%+v err=%v", result, err)
	}
	restricted, err = projection.RestrictedSubjects(ctx, []string{"persona-restricted"})
	if err != nil || restricted["persona-restricted"] {
		t.Fatalf("restored restriction read=%v err=%v", restricted, err)
	}

	stale := suspended
	stale.EventID = "event-stale-suspend-6"
	stale.AccountVersion = 6
	stale.AuthEpoch = 6
	stale.DecisionRef = "decision-stale-6"
	stale.OccurredAt = occurredAt.Add(-time.Minute)
	result, err = projection.Apply(ctx, stale)
	if err != nil || !result.Replayed || !result.Stale || result.Affected != 0 {
		t.Fatalf("stale result=%+v err=%v", result, err)
	}
}
