// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

type notificationRestrictionProjectionSpy struct {
	events []accountrestriction.Event
}

func (spy *notificationRestrictionProjectionSpy) Apply(
	_ context.Context,
	event accountrestriction.Event,
) (application.UserAccountRestrictionProjectionResult, error) {
	spy.events = append(spy.events, event)
	return application.UserAccountRestrictionProjectionResult{}, nil
}

type notificationClosureProjectionStub struct{}

func (notificationClosureProjectionStub) ApplyUserAccountClosed(
	context.Context,
	application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	return application.UserAccountClosedProjectionResult{}, nil
}

type notificationFailureStoreStub struct{}

func (notificationFailureStoreStub) RecordUserAccountClosedFailure(
	context.Context,
	string,
	string,
	string,
	string,
	error,
) (int64, error) {
	return 1, nil
}

func (notificationFailureStoreStub) IsUserAccountClosedDeadLettered(
	context.Context,
	string,
	string,
) (bool, error) {
	return false, nil
}

func (notificationFailureStoreStub) MarkUserAccountClosedDeadLettered(
	context.Context,
	string,
	string,
) error {
	return nil
}

func (notificationFailureStoreStub) ClearUserAccountClosedFailure(
	context.Context,
	string,
	string,
) error {
	return nil
}

func TestNotificationConsumerAppliesUserAccountRestrictionInsteadOfIgnoringIt(
	t *testing.T,
) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	config := streamadapter.DefaultUserAccountClosedConsumerConfig()
	config.MinIdle = 0
	config.MaxAttempts = 3
	config.PollInterval = time.Millisecond
	consumer, err := streamadapter.NewUserAccountClosedConsumer(
		transport,
		notificationClosureProjectionStub{},
		notificationFailureStoreStub{},
		"notification-account-restriction-contract",
		nil,
		config,
	)
	if err != nil {
		t.Fatal(err)
	}
	projection := &notificationRestrictionProjectionSpy{}
	consumer.WithUserAccountRestrictionProjection(projection)
	if _, err := client.XAdd(
		ctx,
		streamadapter.UserAccountEventStream,
		notificationRestrictionEventValues(),
	); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("restriction event processed=%d err=%v", processed, err)
	}
	if len(projection.events) != 1 || !projection.events[0].Restricted() ||
		projection.events[0].AccountVersion != 10 {
		t.Fatalf("restriction projection events=%+v", projection.events)
	}
}

func notificationRestrictionEventValues() map[string]string {
	return map[string]string{
		"eventId":        "notification-suspend-event-10",
		"eventName":      accountrestriction.UserSuspendedEventName,
		"accountId":      "notification-account-suspended",
		"accountVersion": "10",
		"occurredAt":     "2026-07-28T10:00:00Z",
		"payload": `{"userId":"notification-account-suspended","personaIds":["notification-persona-suspended"],` +
			`"accountState":"suspended","authEpoch":10,"decisionRef":"notification-decision-10",` +
			`"occurredAt":"2026-07-28T10:00:00Z"}`,
	}
}
