// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package accountclosure_test

import (
	"context"
	"encoding/json"
	"slices"
	"strconv"
	"sync"
	"testing"
	"time"

	accountrestriction "quwoquan_service/runtime/accountrestriction"
	rtredis "quwoquan_service/runtime/redis"
	accountclosureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
	. "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
)

type accountRestrictionProjectionForTest struct {
	mu     sync.Mutex
	events []accountrestriction.Event
	err    error
}

func (projection *accountRestrictionProjectionForTest) Apply(
	_ context.Context,
	event accountrestriction.Event,
) (accountclosureapp.UserAccountRestrictionProjectionResult, error) {
	projection.mu.Lock()
	defer projection.mu.Unlock()
	projection.events = append(projection.events, event)
	return accountclosureapp.UserAccountRestrictionProjectionResult{}, projection.err
}

func (projection *accountRestrictionProjectionForTest) applied() []accountrestriction.Event {
	projection.mu.Lock()
	defer projection.mu.Unlock()
	return append([]accountrestriction.Event(nil), projection.events...)
}

func TestConsumerAppliesCanonicalAccountRestrictionAndAcknowledges(t *testing.T) {
	redis := newRecordingRedisForTest()
	failures := newFailureStoreForTest()
	projection := &accountRestrictionProjectionForTest{}
	consumer := newConsumerForTest(
		t,
		redis,
		&eventProcessorForTest{},
		failures,
		3,
	).WithAccountRestrictionProjection(projection)
	messageID := appendAccountRestrictionMessageForTest(
		t,
		redis,
		"event-suspend-content",
		accountrestriction.UserSuspendedEventName,
		7,
	)

	processed, err := consumer.ProcessOnce(t.Context())
	if err != nil || processed != 1 {
		t.Fatalf("consume suspension: processed=%d err=%v", processed, err)
	}
	if !slices.Contains(redis.acknowledged(), messageID) {
		t.Fatal("applied restriction event was not acknowledged")
	}
	events := projection.applied()
	if len(events) != 1 || !events[0].Restricted() ||
		events[0].AccountVersion != 7 || events[0].AuthEpoch != 9 {
		t.Fatalf("projection events=%+v", events)
	}
}

func TestConsumerRestrictionConflictRetriesThenMovesToSanitizedDLQ(t *testing.T) {
	redis := newRecordingRedisForTest()
	failures := newFailureStoreForTest()
	projection := &accountRestrictionProjectionForTest{
		err: accountclosureapp.ErrUserAccountRestrictionProjectionConflict,
	}
	consumer := newConsumerForTest(
		t,
		redis,
		&eventProcessorForTest{},
		failures,
		2,
	).WithAccountRestrictionProjection(projection)
	messageID := appendAccountRestrictionMessageForTest(
		t,
		redis,
		"event-conflict-content",
		accountrestriction.UserSuspendedEventName,
		8,
	)

	if _, err := consumer.ProcessOnce(t.Context()); err == nil {
		t.Fatal("first projection conflict must remain pending")
	}
	processed, err := consumer.ProcessOnce(t.Context())
	if err != nil || processed != 1 {
		t.Fatalf("terminal projection conflict: processed=%d err=%v", processed, err)
	}
	if slices.Contains(redis.acknowledged(), messageID) {
		t.Fatal("dead-lettered restriction event was acknowledged")
	}
	if got := redis.expiration(DeadLetterStream); got != DeadLetterRetention {
		t.Fatalf("restriction DLQ retention=%s", got)
	}
}

func TestConsumerRejectsRestrictionPayloadDriftWithoutApplying(t *testing.T) {
	redis := newRecordingRedisForTest()
	failures := newFailureStoreForTest()
	projection := &accountRestrictionProjectionForTest{}
	consumer := newConsumerForTest(
		t,
		redis,
		&eventProcessorForTest{},
		failures,
		1,
	).WithAccountRestrictionProjection(projection)
	occurredAt := time.Date(2026, 7, 29, 4, 0, 0, 0, time.UTC)
	messageID, err := redis.XAdd(t.Context(), UserAccountEventStream, map[string]string{
		"eventId":        "event-invalid-content",
		"eventName":      accountrestriction.UserRestoredEventName,
		"accountId":      "account-content",
		"accountVersion": "9",
		"occurredAt":     occurredAt.Format(time.RFC3339Nano),
		"payload": `{"userId":"account-content","personaIds":["persona-content"],` +
			`"accountState":"active","authEpoch":10,"decisionRef":"decision-restore",` +
			`"occurredAt":"2026-07-29T04:00:00Z","caseRef":"must-not-cross"}`,
	})
	if err != nil {
		t.Fatal(err)
	}
	processed, err := consumer.ProcessOnce(t.Context())
	if err != nil || processed != 1 {
		t.Fatalf("invalid restriction DLQ: processed=%d err=%v", processed, err)
	}
	if len(projection.applied()) != 0 {
		t.Fatalf("invalid restriction reached projection: %+v", projection.applied())
	}
	if slices.Contains(redis.acknowledged(), messageID) {
		t.Fatal("invalid restriction was acknowledged")
	}
}

func appendAccountRestrictionMessageForTest(
	t *testing.T,
	redis rtredis.Client,
	eventID string,
	eventName string,
	accountVersion int64,
) string {
	t.Helper()
	occurredAt := time.Date(2026, 7, 29, 4, 0, 0, 0, time.UTC)
	state := "suspended"
	if eventName == accountrestriction.UserRestoredEventName {
		state = "active"
	}
	payload, err := json.Marshal(map[string]any{
		"userId":       "account-content",
		"personaIds":   []string{"persona-content"},
		"accountState": state,
		"authEpoch":    int64(9),
		"decisionRef":  "decision-content",
		"occurredAt":   occurredAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	messageID, err := redis.XAdd(t.Context(), UserAccountEventStream, map[string]string{
		"eventId":        eventID,
		"eventName":      eventName,
		"accountId":      "account-content",
		"accountVersion": strconv.FormatInt(accountVersion, 10),
		"payload":        string(payload),
		"occurredAt":     occurredAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	return messageID
}
