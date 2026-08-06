// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
// readiness_case: apply-search-account-restriction-local
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/accountrestriction"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	consumer "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/mq"
	indexapplication "quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

func TestSearchIndexRestrictionRunnerExecutesConsumerAndAcknowledges(t *testing.T) {
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatal(err)
	}
	restrictions := &restrictionRecorder{}
	runner, err := consumer.NewUserAccountRestrictionConsumer(
		transport, restrictions, "search-index-restriction-local", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	messageID, err := transport.AppendDurable(t.Context(), runtimemessaging.DurableMessage{
		Stream: consumer.UserAccountEventStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: "search-index-suspend-7"},
			{Name: "eventName", Value: accountrestriction.UserSuspendedEventName},
			{Name: "accountId", Value: "account-7"},
			{Name: "accountVersion", Value: "7"},
			{Name: "occurredAt", Value: "2026-08-05T08:00:00Z"},
			{Name: "payload", Value: `{"userId":"account-7","personaIds":["persona-7"],"accountState":"suspended","authEpoch":7,"decisionRef":"decision-7","occurredAt":"2026-08-05T08:00:00Z"}`},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	processed, err := runner.ProcessOnce(t.Context())
	if err != nil || processed != 1 || len(restrictions.events) != 1 ||
		!restrictions.events[0].Restricted() {
		t.Fatalf("processed=%d events=%+v err=%v", processed, restrictions.events, err)
	}
	pending, _, err := redis.XAutoClaim(
		t.Context(), consumer.UserAccountEventStream,
		consumer.UserAccountRestrictionConsumerGroup, "ack-inspector", 0, "0-0", 10,
	)
	if err != nil || len(pending) != 0 {
		t.Fatalf("message %s was not acknowledged: pending=%+v err=%v", messageID, pending, err)
	}
}

type restrictionRecorder struct{ events []accountrestriction.Event }

func (recorder *restrictionRecorder) Apply(
	_ context.Context,
	event accountrestriction.Event,
) (indexapplication.UserAccountRestrictionProjectionResult, error) {
	recorder.events = append(recorder.events, event)
	return indexapplication.UserAccountRestrictionProjectionResult{}, nil
}
