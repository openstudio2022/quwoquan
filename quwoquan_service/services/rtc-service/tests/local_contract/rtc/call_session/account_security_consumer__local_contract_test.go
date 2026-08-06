// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// readiness_case: recover-rtc-account-closure-dead-letter-local
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/mq"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/cache"
)

func TestAccountSecurityConsumerRetriesDeadLettersWithoutPIIAndRecovers(
	t *testing.T,
) {
	t.Parallel()

	const (
		accountID = "account-sensitive-42"
		personaID = "persona-sensitive-42"
		eventID   = "event-sensitive-42"
	)
	delivery := runtimemessaging.StreamDelivery{
		Stream: mq.UserAccountSecurityEventStream,
		ID:     "1710000000000-42",
		Fields: []runtimemessaging.DurableField{
			{Name: "eventName", Value: "UserAccountClosed"},
			{Name: "eventId", Value: eventID},
			{Name: "accountId", Value: accountID},
			{Name: "accountVersion", Value: "1"},
			{Name: "occurredAt", Value: "2026-07-23T14:30:00Z"},
			{Name: "payload", Value: `{"userId":"account-sensitive-42","personaIds":["persona-sensitive-42"],"accountState":"closed","updatedAt":"2026-07-23T14:30:00Z"}`},
		},
	}
	transport := &terminalConsumerTransport{delivery: delivery}
	failures := &terminalConsumerFailures{}
	closer := &terminalConsumerCloser{failuresRemaining: 2}
	consumer, err := mq.NewUserAccountSecurityConsumer(
		transport,
		closer,
		failures,
		"rtc-security-local-contract",
		nil,
		mq.UserAccountSecurityConsumerConfig{
			BatchSize:   1,
			MaxAttempts: 2,
			MinIdle:     time.Second,
			ReadBlock:   0,
		},
	)
	if err != nil {
		t.Fatalf("NewUserAccountSecurityConsumer() error = %v", err)
	}

	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("first terminal-closure failure was acknowledged")
	}
	if transport.deadLetter != nil {
		t.Fatal("first failure reached DLQ before retry budget was exhausted")
	}
	if transport.wasAcked(delivery.ID) {
		t.Fatal("first failure acknowledged the source PEL entry")
	}
	if err := consumer.RecoverDeadLetter(context.Background(), delivery.ID); err != nil {
		t.Fatalf("non-terminal recovery must be an idempotent no-op: %v", err)
	}

	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("second failure ProcessOnce() = (%d, %v), want DLQ acknowledgement", processed, err)
	}
	if transport.deadLetter == nil {
		t.Fatal("retry exhaustion did not publish a dead letter")
	}
	if transport.deadLetter.DestinationStream != mq.UserAccountSecurityDLQ {
		t.Fatalf("DLQ destination = %q", transport.deadLetter.DestinationStream)
	}
	if transport.wasAcked(delivery.ID) {
		t.Fatal("DLQ source entry was acknowledged instead of retained for recovery")
	}
	for _, field := range transport.deadLetter.Fields {
		if strings.Contains(field.Value, accountID) ||
			strings.Contains(field.Value, personaID) ||
			strings.Contains(field.Value, eventID) ||
			strings.Contains(field.Value, "userId") {
			t.Fatalf("DLQ field %q leaked PII or source payload: %q", field.Name, field.Value)
		}
	}

	if err := consumer.RecoverDeadLetter(context.Background(), delivery.ID); err != nil {
		t.Fatalf("RecoverDeadLetter() error = %v", err)
	}
	closer.failuresRemaining = 0
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("recovered ProcessOnce() = (%d, %v), want successful replay", processed, err)
	}
	if !transport.wasAcked(delivery.ID) {
		t.Fatal("recovered source entry was not acknowledged")
	}
	if closer.applied != 1 {
		t.Fatalf("successful recovered applies = %d, want 1", closer.applied)
	}
	if closer.last.AccountState != "closed" ||
		closer.last.AccountID != accountID ||
		len(closer.last.PersonaIDs) != 1 ||
		closer.last.PersonaIDs[0] != personaID {
		t.Fatalf("recovered terminal event projection = %#v", closer.last)
	}
}

func TestAccountSecurityFailureStoreRequiresDurableSourcePELReference(
	t *testing.T,
) {
	t.Parallel()
	const (
		stream    = "events.user.account"
		messageID = "1710000000000-84"
	)
	store := cache.NewAccountSecurityEventFailureStore(
		rtredis.NewMemoryClient(),
	)
	if err := store.MarkAccountSecurityDeadLettered(
		t.Context(),
		stream,
		messageID,
	); err == nil || !strings.Contains(err.Error(), "source PEL reference") {
		t.Fatalf("terminal marker without source reference was accepted: %v", err)
	}
	if attempts, err := store.RecordAccountSecurityFailure(
		t.Context(),
		stream,
		messageID,
		"event-84",
		"dependency",
		errors.New("media access revocation unavailable"),
	); err != nil || attempts != 1 {
		t.Fatalf("record source failure: attempts=%d err=%v", attempts, err)
	}
	if err := store.MarkAccountSecurityDeadLettered(
		t.Context(),
		stream,
		messageID,
	); err != nil {
		t.Fatalf("mark source PEL held: %v", err)
	}
	if _, err := store.RecordAccountSecurityFailure(
		t.Context(),
		stream,
		messageID,
		"event-84",
		"dependency",
		errors.New("late retry"),
	); err == nil || !strings.Contains(err.Error(), "held for recovery") {
		t.Fatalf("terminal marker allowed automatic retry: %v", err)
	}
}

type terminalConsumerCloser struct {
	failuresRemaining int
	applied           int
	last              application.AccountSecurityTerminalEvent
}

func (closer *terminalConsumerCloser) ApplyAccountSecurityTerminalEvent(
	_ context.Context,
	event application.AccountSecurityTerminalEvent,
) (application.AccountSecurityTerminalApplyResult, error) {
	if closer.failuresRemaining > 0 {
		closer.failuresRemaining--
		return application.AccountSecurityTerminalApplyResult{},
			errors.New("terminal room revocation failed")
	}
	closer.applied++
	closer.last = event
	return application.AccountSecurityTerminalApplyResult{TerminatedCalls: 1}, nil
}

type terminalConsumerFailures struct {
	attempts map[string]int64
	dead     map[string]bool
}

func (store *terminalConsumerFailures) RecordAccountSecurityFailure(
	_ context.Context,
	_ string,
	messageID string,
	_ string,
	_ string,
	_ error,
) (int64, error) {
	if store.attempts == nil {
		store.attempts = make(map[string]int64)
	}
	store.attempts[messageID]++
	return store.attempts[messageID], nil
}

func (store *terminalConsumerFailures) IsAccountSecurityDeadLettered(
	_ context.Context,
	_ string,
	messageID string,
) (bool, error) {
	return store.dead != nil && store.dead[messageID], nil
}

func (store *terminalConsumerFailures) MarkAccountSecurityDeadLettered(
	_ context.Context,
	_ string,
	messageID string,
) error {
	if store.dead == nil {
		store.dead = make(map[string]bool)
	}
	store.dead[messageID] = true
	return nil
}

func (store *terminalConsumerFailures) ClearAccountSecurityFailure(
	_ context.Context,
	_ string,
	messageID string,
) error {
	delete(store.attempts, messageID)
	delete(store.dead, messageID)
	return nil
}

type terminalConsumerTransport struct {
	delivery   runtimemessaging.StreamDelivery
	acked      map[string]bool
	deadLetter *runtimemessaging.DeadLetterMessage
}

func (*terminalConsumerTransport) PublishEphemeral(
	context.Context,
	runtimemessaging.EphemeralMessage,
) error {
	return nil
}

func (*terminalConsumerTransport) SubscribeEphemeral(
	context.Context,
	...string,
) (runtimemessaging.EphemeralSubscription, error) {
	return nil, errors.New("ephemeral subscribe is not used by account security consumer")
}

func (*terminalConsumerTransport) AppendDurable(
	context.Context,
	runtimemessaging.DurableMessage,
) (string, error) {
	return "", errors.New("durable append is not used by account security consumer")
}

func (*terminalConsumerTransport) EnsureDurableConsumerGroup(
	context.Context,
	string,
	string,
	string,
) error {
	return nil
}

func (transport *terminalConsumerTransport) ReadDurable(
	_ context.Context,
	_ runtimemessaging.StreamReadRequest,
) ([]runtimemessaging.StreamDelivery, error) {
	if transport.wasAcked(transport.delivery.ID) {
		return nil, nil
	}
	return []runtimemessaging.StreamDelivery{transport.delivery}, nil
}

func (transport *terminalConsumerTransport) AckDurable(
	_ context.Context,
	_ string,
	_ string,
	ids ...string,
) error {
	if transport.acked == nil {
		transport.acked = make(map[string]bool)
	}
	for _, id := range ids {
		transport.acked[id] = true
	}
	return nil
}

func (*terminalConsumerTransport) ReclaimDurable(
	context.Context,
	string,
	string,
	string,
	time.Duration,
	string,
	int64,
) ([]runtimemessaging.StreamDelivery, string, error) {
	return nil, "0-0", nil
}

func (transport *terminalConsumerTransport) PublishDeadLetter(
	_ context.Context,
	message runtimemessaging.DeadLetterMessage,
) (string, error) {
	copy := message
	copy.Fields = append([]runtimemessaging.DurableField(nil), message.Fields...)
	transport.deadLetter = &copy
	return "1720000000000-1", nil
}

func (*terminalConsumerTransport) ClaimDurableDelivery(
	context.Context,
	string,
	string,
	time.Duration,
) (bool, error) {
	return true, nil
}

func (*terminalConsumerTransport) ReleaseDurableDelivery(
	context.Context,
	string,
) error {
	return nil
}

func (*terminalConsumerTransport) SetDurableRetention(
	context.Context,
	string,
	time.Duration,
) error {
	return nil
}

func (transport *terminalConsumerTransport) wasAcked(id string) bool {
	return transport.acked != nil && transport.acked[id]
}

var _ mq.AccountSecurityDurableTransport = (*terminalConsumerTransport)(nil)
var _ mq.AccountSecurityFailureStore = (*terminalConsumerFailures)(nil)
var _ application.AccountSecurityTerminalCloser = (*terminalConsumerCloser)(nil)
