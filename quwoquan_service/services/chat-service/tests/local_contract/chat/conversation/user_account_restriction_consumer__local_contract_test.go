// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/accountrestriction"
	rtredis "quwoquan_service/runtime/redis"
	mqadapter "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

type chatRestrictionProjectionSpy struct {
	events []accountrestriction.Event
}

func (spy *chatRestrictionProjectionSpy) Apply(
	_ context.Context,
	event accountrestriction.Event,
) (application.UserAccountRestrictionProjectionResult, error) {
	spy.events = append(spy.events, event)
	return application.UserAccountRestrictionProjectionResult{}, nil
}

func TestChatConsumerAppliesUserAccountRestrictionInsteadOfIgnoringIt(
	t *testing.T,
) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	consumer := newUserAccountClosedConsumerForTest(
		t,
		client,
		&memoryUserAccountClosedProjection{},
		&memoryUserAccountClosedFailures{},
		nil,
		3,
	)
	projection := &chatRestrictionProjectionSpy{}
	consumer.WithUserAccountRestrictionProjection(projection)
	if _, err := client.XAdd(
		ctx,
		mqadapter.UserAccountEventStream,
		chatRestrictionEventValues(),
	); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("restriction event processed=%d err=%v", processed, err)
	}
	if len(projection.events) != 1 || !projection.events[0].Restricted() ||
		projection.events[0].AccountVersion != 8 {
		t.Fatalf("restriction projection events=%+v", projection.events)
	}
}

func chatRestrictionEventValues() map[string]string {
	return map[string]string{
		"eventId":        "chat-suspend-event-8",
		"eventName":      accountrestriction.UserSuspendedEventName,
		"accountId":      "chat-account-suspended",
		"accountVersion": "8",
		"occurredAt":     "2026-07-28T08:00:00Z",
		"payload": `{"userId":"chat-account-suspended","personaIds":["chat-persona-suspended"],` +
			`"accountState":"suspended","authEpoch":8,"decisionRef":"chat-decision-8",` +
			`"occurredAt":"2026-07-28T08:00:00Z"}`,
	}
}
