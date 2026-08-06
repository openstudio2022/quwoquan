// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// readiness_case: recover-chat-account-closure-dead-letter-local
package local_contract

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

type memoryUserAccountClosedProjection struct {
	err      error
	digests  map[string]string
	calls    int
	replayed int
}

func (projection *memoryUserAccountClosedProjection) ApplyUserAccountClosed(
	_ context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedApplyResult, error) {
	projection.calls++
	if projection.err != nil {
		return application.UserAccountClosedApplyResult{}, projection.err
	}
	if projection.digests == nil {
		projection.digests = map[string]string{}
	}
	if digest, found := projection.digests[event.EventID]; found {
		if digest != event.Digest() {
			return application.UserAccountClosedApplyResult{},
				errors.New("eventId conflict")
		}
		projection.replayed++
		return application.UserAccountClosedApplyResult{Replayed: true}, nil
	}
	projection.digests[event.EventID] = event.Digest()
	return application.UserAccountClosedApplyResult{}, nil
}

type memoryUserAccountClosedFailures struct {
	attempts     map[string]int64
	deadLettered map[string]bool
}

type expireTrackingRedis struct {
	rtredis.Client
	expired map[string]time.Duration
}

func (client *expireTrackingRedis) Expire(
	ctx context.Context,
	key string,
	ttl time.Duration,
) error {
	if client.expired == nil {
		client.expired = map[string]time.Duration{}
	}
	client.expired[key] = ttl
	return client.Client.Expire(ctx, key, ttl)
}

func (store *memoryUserAccountClosedFailures) RecordUserAccountClosedFailure(
	_ context.Context,
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

func (store *memoryUserAccountClosedFailures) ClearUserAccountClosedFailure(
	_ context.Context,
	messageID string,
) error {
	delete(store.attempts, messageID)
	delete(store.deadLettered, messageID)
	return nil
}

func (store *memoryUserAccountClosedFailures) IsUserAccountClosedDeadLettered(
	_ context.Context,
	messageID string,
) (bool, error) {
	return store.deadLettered[messageID], nil
}

func (store *memoryUserAccountClosedFailures) MarkUserAccountClosedDeadLettered(
	_ context.Context,
	messageID string,
) error {
	if store.deadLettered == nil {
		store.deadLettered = map[string]bool{}
	}
	store.deadLettered[messageID] = true
	return nil
}

func TestUserAccountClosedConsumerAppliesAndAcknowledgesReplay(
	t *testing.T,
) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	projection := &memoryUserAccountClosedProjection{}
	failures := &memoryUserAccountClosedFailures{}
	consumer := newUserAccountClosedConsumerForTest(
		t,
		client,
		projection,
		failures,
		slog.Default(),
		2,
	)
	values := validUserAccountClosedValues("event-close-replay")
	if _, err := client.XAdd(ctx, UserAccountEventStream, values); err != nil {
		t.Fatal(err)
	}
	if _, err := client.XAdd(ctx, UserAccountEventStream, values); err != nil {
		t.Fatal(err)
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("process normal and replayed closure: %v", err)
	}
	if processed != 2 || projection.calls != 2 || projection.replayed != 1 {
		t.Fatalf(
			"processed=%d calls=%d replayed=%d",
			processed,
			projection.calls,
			projection.replayed,
		)
	}
	if err := consumer.Healthy(time.Second); err != nil {
		t.Fatalf("successful scan must be healthy: %v", err)
	}
}

func TestUserAccountClosedConsumerRetriesWithoutAckThenDeadLetters(
	t *testing.T,
) {
	ctx := context.Background()
	client := &expireTrackingRedis{Client: rtredis.NewMemoryClient()}
	secret := "persona-secret-must-not-be-logged"
	projection := &memoryUserAccountClosedProjection{}
	failures := &memoryUserAccountClosedFailures{}
	var logOutput bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&logOutput, nil))
	consumer := newUserAccountClosedConsumerForTest(
		t,
		client,
		projection,
		failures,
		logger,
		2,
	)
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 0 {
		t.Fatalf("initial empty scan must establish health, processed=%d err=%v", processed, err)
	}
	projection.err = errors.New("projection failed for " + secret)
	messageID, err := client.XAdd(
		ctx,
		UserAccountEventStream,
		validUserAccountClosedValues("event-close-failure"),
	)
	if err != nil {
		t.Fatal(err)
	}

	if processed, err := consumer.ProcessOnce(ctx); err == nil || processed != 0 {
		t.Fatalf("first failure must remain pending, processed=%d err=%v", processed, err)
	}
	if err := consumer.RecoverDeadLetter(ctx, messageID); err != nil {
		t.Fatalf("non-terminal recovery must be an idempotent no-op: %v", err)
	}
	healthErr := consumer.Healthy(time.Second)
	if healthErr == nil {
		t.Fatal("failed consumer health must expose a sanitized failure signal")
	}
	if strings.Contains(healthErr.Error(), secret) ||
		!strings.Contains(healthErr.Error(), "digest") {
		t.Fatalf("consumer health leaked private identity: %v", healthErr)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("second failure must reach DLQ, processed=%d err=%v", processed, err)
	}
	if !failures.deadLettered[messageID] {
		t.Fatalf(
			"terminal DLQ must retain a recovery marker: %#v",
			failures.deadLettered,
		)
	}
	pending, _, err := client.XAutoClaim(
		ctx,
		UserAccountEventStream,
		"chat-service-user-account-closed",
		"chat-closure-pending-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil || len(pending) != 1 {
		t.Fatalf("terminal DLQ must retain source PEL: pending=%+v err=%v", pending, err)
	}
	if err := consumer.RecoverDeadLetter(ctx, pending[0].ID); err != nil {
		t.Fatalf("release source PEL: %v", err)
	}
	if failures.deadLettered[pending[0].ID] {
		t.Fatal("recovery must release terminal marker")
	}
	if strings.Contains(logOutput.String(), secret) {
		t.Fatalf("consumer log leaked private identity: %s", logOutput.String())
	}
}

func TestUserAccountClosedConsumerRunBecomesHealthyAndStopsOnCancel(
	t *testing.T,
) {
	client := rtredis.NewMemoryClient()
	consumer := newUserAccountClosedConsumerForTest(
		t,
		client,
		&memoryUserAccountClosedProjection{},
		&memoryUserAccountClosedFailures{},
		slog.Default(),
		2,
	)
	ctx, cancel := context.WithCancel(context.Background())
	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		consumer.Run(ctx)
	}()
	deadline := time.Now().Add(time.Second)
	for consumer.Healthy(time.Second) != nil && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if err := consumer.Healthy(time.Second); err != nil {
		cancel()
		t.Fatalf("running consumer did not become healthy: %v", err)
	}
	cancel()
	select {
	case <-stopped:
	case <-time.After(time.Second):
		t.Fatal("consumer did not stop after context cancellation")
	}
}

func newUserAccountClosedConsumerForTest(
	t *testing.T,
	client rtredis.Client,
	projection application.UserAccountClosedProjection,
	failures UserAccountClosedFailureStore,
	logger *slog.Logger,
	maxAttempts int64,
) *UserAccountClosedConsumer {
	t.Helper()
	consumer, err := NewUserAccountClosedConsumer(
		client,
		projection,
		failures,
		"chat-close-test",
		logger,
		UserAccountClosedConsumerConfig{
			BatchSize:    10,
			MaxAttempts:  maxAttempts,
			MinIdle:      0,
			PollInterval: time.Millisecond,
			ReadBlock:    0,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := consumer.EnsureGroup(context.Background()); err != nil {
		t.Fatal(err)
	}
	return consumer
}

func validUserAccountClosedValues(eventID string) map[string]string {
	return map[string]string{
		"eventId":        eventID,
		"eventName":      application.UserAccountClosedEventName,
		"accountId":      "account-private",
		"accountVersion": "7",
		"payload": `{
			"userId":"account-private",
			"personaIds":["persona-private-b","persona-private-a"],
			"accountState":"closed",
			"updatedAt":"2026-07-20T12:00:00Z"
		}`,
		"occurredAt": "2026-07-20T12:00:00Z",
	}
}
