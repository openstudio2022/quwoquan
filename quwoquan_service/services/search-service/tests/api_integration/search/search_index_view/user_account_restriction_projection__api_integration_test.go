// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
// readiness_case: apply-search-account-restriction-api
package api_integration

import (
	"errors"
	"testing"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	runtimemessaging "quwoquan_service/runtime/messaging"
	consumer "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/mq"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
	accountrestrictioninfra "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/accountrestriction"
)

func TestUserAccountRestrictionConsumerPersistsAndAcknowledgesRealMongoProjection(t *testing.T) {
	cleanSearchCollections(t)
	projection, err := accountrestrictioninfra.NewMongoAccountRestrictionProjection(mongoDB)
	if err != nil {
		t.Fatal(err)
	}
	if err := projection.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	transport, err := runtimemessaging.NewRedisMessageTransport(
		realRedisClient,
		realRedisClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	runner, err := consumer.NewUserAccountRestrictionConsumer(
		transport, projection, "search-index-restriction-api", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := transport.AppendDurable(t.Context(), runtimemessaging.DurableMessage{
		Stream: consumer.UserAccountEventStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: "search-index-api-suspend-9"},
			{Name: "eventName", Value: accountrestriction.UserSuspendedEventName},
			{Name: "accountId", Value: "account-api-9"},
			{Name: "accountVersion", Value: "9"},
			{Name: "occurredAt", Value: "2026-08-05T09:00:00Z"},
			{Name: "payload", Value: `{"userId":"account-api-9","personaIds":["persona-api-9"],"accountState":"suspended","authEpoch":9,"decisionRef":"decision-api-9","occurredAt":"2026-08-05T09:00:00Z"}`},
		},
	}); err != nil {
		t.Fatal(err)
	}
	processed, err := runner.ProcessOnce(t.Context())
	if err != nil || processed != 1 {
		t.Fatalf("ProcessOnce() processed=%d err=%v", processed, err)
	}
	restricted, err := projection.RestrictedSubjects(t.Context(), []string{"persona-api-9"})
	if err != nil || !restricted["persona-api-9"] {
		t.Fatalf("restriction=%v err=%v", restricted, err)
	}
}

func TestUserAccountRestrictionProjectionIsReversibleMonotonicAndReplaySafe(
	t *testing.T,
) {
	cleanSearchCollections(t)
	ctx := t.Context()
	projection, err := accountrestrictioninfra.NewMongoAccountRestrictionProjection(mongoDB)
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
