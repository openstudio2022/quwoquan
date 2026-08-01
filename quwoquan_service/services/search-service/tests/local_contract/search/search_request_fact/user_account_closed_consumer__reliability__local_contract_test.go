// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	indexapplication "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	consumer "quwoquan_service/services/search-service/internal/search/search_request_fact/adapters/inbound/mq"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application"
)

type failingClosureProjection struct{}

func (failingClosureProjection) ApplyUserAccountClosed(
	context.Context,
	application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	return application.UserAccountClosedProjectionResult{},
		errors.New("projection failed for private subject")
}

type noopClosureProjection struct{}

func (noopClosureProjection) ApplyUserAccountClosed(
	context.Context,
	application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	return application.UserAccountClosedProjectionResult{}, nil
}

type recordingRestrictionProjection struct {
	events []accountrestriction.Event
}

func (projection *recordingRestrictionProjection) Apply(
	_ context.Context,
	event accountrestriction.Event,
) (indexapplication.UserAccountRestrictionProjectionResult, error) {
	projection.events = append(projection.events, event)
	return indexapplication.UserAccountRestrictionProjectionResult{}, nil
}

type closureFailureStore struct {
	attempts map[string]int64
	dead     map[string]bool
}

func (store *closureFailureStore) RecordUserAccountClosedFailure(
	_ context.Context,
	_ string,
	messageID string,
	_ string,
	_ error,
) (int64, error) {
	if store.attempts == nil {
		store.attempts = map[string]int64{}
	}
	store.attempts[messageID]++
	return store.attempts[messageID], nil
}

func (store *closureFailureStore) ClearUserAccountClosedFailure(
	_ context.Context,
	_ string,
	messageID string,
) error {
	delete(store.attempts, messageID)
	delete(store.dead, messageID)
	return nil
}

func (store *closureFailureStore) IsUserAccountClosedDeadLettered(
	_ context.Context,
	_ string,
	messageID string,
) (bool, error) {
	return store.dead[messageID], nil
}

func (store *closureFailureStore) MarkUserAccountClosedDeadLettered(
	_ context.Context,
	_ string,
	messageID string,
) error {
	if store.dead == nil {
		store.dead = map[string]bool{}
	}
	store.dead[messageID] = true
	return nil
}

func TestUserAccountClosedTerminalDLQRetainsSourcePELForRecovery(t *testing.T) {
	ctx := t.Context()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatal(err)
	}
	failures := &closureFailureStore{}
	instance, err := consumer.NewUserAccountClosedConsumer(
		transport,
		failingClosureProjection{},
		failures,
		"search-account-closure-contract",
		nil,
		consumer.UserAccountClosedConsumerConfig{
			BatchSize: 10, MaxAttempts: 2, MinIdle: 0,
			PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	payload := `{"userId":"account-private","personaIds":[],"accountState":"closed","updatedAt":"2026-07-20T12:00:00Z"}`
	messageID, err := transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: consumer.UserAccountEventStream,
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: "event-private"},
				{Name: "eventName", Value: application.UserAccountClosedEventName},
				{Name: "accountId", Value: "account-private"},
				{Name: "accountVersion", Value: "7"},
				{Name: "occurredAt", Value: "2026-07-20T12:00:00Z"},
				{Name: "payload", Value: payload},
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if processed, err := instance.ProcessOnce(ctx); err == nil || processed != 0 {
		t.Fatalf("first failure: processed=%d err=%v", processed, err)
	}
	if err := instance.RecoverDeadLetter(ctx, messageID); err != nil {
		t.Fatalf("non-terminal recovery must be an idempotent no-op: %v", err)
	}
	if processed, err := instance.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("terminal DLQ transition: processed=%d err=%v", processed, err)
	}
	if !failures.dead[messageID] {
		t.Fatalf("terminal source marker missing: %+v", failures.dead)
	}
	pending, _, err := redis.XAutoClaim(
		ctx,
		consumer.UserAccountEventStream,
		consumer.UserAccountClosedConsumerGroup,
		"search-account-closure-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil || len(pending) != 1 || pending[0].ID != messageID {
		t.Fatalf("terminal source PEL: pending=%+v err=%v", pending, err)
	}
	if err := instance.RecoverDeadLetter(ctx, messageID); err != nil {
		t.Fatalf("release terminal source PEL: %v", err)
	}
	if failures.dead[messageID] {
		t.Fatal("recovery must clear terminal marker")
	}
}

func TestUserAccountRestrictionEventIsAppliedAndAcknowledged(t *testing.T) {
	ctx := t.Context()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatal(err)
	}
	projection := &recordingRestrictionProjection{}
	instance, err := consumer.NewUserAccountClosedConsumer(
		transport,
		noopClosureProjection{},
		&closureFailureStore{},
		"search-account-restriction-contract",
		nil,
		consumer.UserAccountClosedConsumerConfig{
			BatchSize: 10, MaxAttempts: 3, MinIdle: 0,
			PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	instance.WithUserAccountRestrictionProjection(projection)
	payload := `{"userId":"account-suspended","personaIds":["persona-suspended"],"accountState":"suspended","authEpoch":4,"decisionRef":"decision-4","occurredAt":"2026-07-28T12:00:00Z"}`
	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: consumer.UserAccountEventStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: "event-suspended-4"},
			{Name: "eventName", Value: accountrestriction.UserSuspendedEventName},
			{Name: "accountId", Value: "account-suspended"},
			{Name: "accountVersion", Value: "4"},
			{Name: "occurredAt", Value: "2026-07-28T12:00:00Z"},
			{Name: "payload", Value: payload},
		},
	}); err != nil {
		t.Fatal(err)
	}
	if processed, err := instance.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("restriction event: processed=%d err=%v", processed, err)
	}
	if len(projection.events) != 1 || !projection.events[0].Restricted() {
		t.Fatalf("restriction projection events: %+v", projection.events)
	}
}

func TestUserAccountClosedConsumerHealthRedactsFailureDetails(t *testing.T) {
	ctx := t.Context()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatal(err)
	}
	instance, err := consumer.NewUserAccountClosedConsumer(
		transport,
		failingClosureProjection{},
		&closureFailureStore{},
		"search-account-closure-health-contract",
		nil,
		consumer.UserAccountClosedConsumerConfig{
			BatchSize: 10, MaxAttempts: 3, MinIdle: 0,
			PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if processed, err := instance.ProcessOnce(ctx); err != nil || processed != 0 {
		t.Fatalf("prime consumer health: processed=%d err=%v", processed, err)
	}
	payload := `{"userId":"search-account-secret","personaIds":["search-persona-secret"],"accountState":"closed","updatedAt":"2026-07-20T12:00:00Z"}`
	if _, err := transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: consumer.UserAccountEventStream,
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: "event-health-redaction"},
				{Name: "eventName", Value: application.UserAccountClosedEventName},
				{Name: "accountId", Value: "search-account-secret"},
				{Name: "accountVersion", Value: "8"},
				{Name: "occurredAt", Value: "2026-07-20T12:00:00Z"},
				{Name: "payload", Value: payload},
			},
		},
	); err != nil {
		t.Fatal(err)
	}
	if _, err := instance.ProcessOnce(ctx); err == nil {
		t.Fatal("failure required to exercise health redaction")
	}
	healthErr := instance.Healthy(time.Second)
	if healthErr == nil {
		t.Fatal("health must report the failed scan")
	}
	for _, secret := range []string{
		"search-account-secret",
		"search-persona-secret",
		"private subject",
	} {
		if strings.Contains(healthErr.Error(), secret) {
			t.Fatalf("health leaked %q: %v", secret, healthErr)
		}
	}
}
