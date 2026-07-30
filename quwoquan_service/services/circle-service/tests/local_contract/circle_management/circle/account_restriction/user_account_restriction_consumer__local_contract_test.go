// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	messaging "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
)

type circleRestrictionProjectionSpy struct {
	events []accountrestriction.Event
}

func (spy *circleRestrictionProjectionSpy) Apply(
	_ context.Context,
	event accountrestriction.Event,
) (application.UserAccountRestrictionProjectionResult, error) {
	spy.events = append(spy.events, event)
	return application.UserAccountRestrictionProjectionResult{}, nil
}

type circleClosureProjectionStub struct{}

func (circleClosureProjectionStub) ApplyUserAccountClosed(
	context.Context,
	application.UserAccountClosedEvent,
) (application.UserAccountClosedApplyResult, error) {
	return application.UserAccountClosedApplyResult{}, nil
}

type circleFailureStoreStub struct{}

func (circleFailureStoreStub) RecordUserAccountClosedFailure(
	context.Context,
	string,
	string,
	error,
) (int64, error) {
	return 1, nil
}

func (circleFailureStoreStub) ClearUserAccountClosedFailure(
	context.Context,
	string,
) error {
	return nil
}

func (circleFailureStoreStub) IsUserAccountClosedDeadLettered(
	context.Context,
	string,
) (bool, error) {
	return false, nil
}

func (circleFailureStoreStub) MarkUserAccountClosedDeadLettered(
	context.Context,
	string,
) error {
	return nil
}

func TestCircleConsumerAppliesUserAccountRestrictionInsteadOfIgnoringIt(
	t *testing.T,
) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := messaging.NewUserAccountClosedConsumerWithConfig(
		transport,
		circleClosureProjectionStub{},
		circleFailureStoreStub{},
		"circle-account-restriction-contract",
		nil,
		messaging.UserAccountClosedConsumerConfig{
			BatchSize: 10, MaxAttempts: 3, MinIdle: 0,
			ReadBlock: 0, PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	projection := &circleRestrictionProjectionSpy{}
	consumer.WithUserAccountRestrictionProjection(projection)
	if _, err := client.XAdd(
		ctx,
		messaging.UserAccountEventStream,
		circleRestrictionEventValues(),
	); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("restriction event processed=%d err=%v", processed, err)
	}
	if len(projection.events) != 1 || !projection.events[0].Restricted() ||
		projection.events[0].AccountVersion != 9 {
		t.Fatalf("restriction projection events=%+v", projection.events)
	}
}

func circleRestrictionEventValues() map[string]string {
	return map[string]string{
		"eventId":        "circle-suspend-event-9",
		"eventName":      accountrestriction.UserSuspendedEventName,
		"accountId":      "circle-account-suspended",
		"accountVersion": "9",
		"occurredAt":     "2026-07-28T09:00:00Z",
		"payload": `{"userId":"circle-account-suspended","personaIds":["circle-persona-suspended"],` +
			`"accountState":"suspended","authEpoch":9,"decisionRef":"circle-decision-9",` +
			`"occurredAt":"2026-07-28T09:00:00Z"}`,
	}
}
