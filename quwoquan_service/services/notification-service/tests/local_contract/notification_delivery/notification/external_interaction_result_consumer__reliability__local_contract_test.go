// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-005

package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
)

type externalResultProjectionFake struct {
	mu        sync.Mutex
	byAttempt map[string]notification.ExternalInteractionResultEvent
}

func (projection *externalResultProjectionFake) RecordExternalInteractionResult(
	_ context.Context,
	event notification.ExternalInteractionResultEvent,
	_ time.Time,
) error {
	projection.mu.Lock()
	defer projection.mu.Unlock()
	if projection.byAttempt == nil {
		projection.byAttempt = map[string]notification.ExternalInteractionResultEvent{}
	}
	projection.byAttempt[event.AttemptID] = event
	return nil
}

func TestExternalInteractionResultConsumerDedupesOwnedReceiptAndKeepsDigestOnly(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatalf("message transport: %v", err)
	}
	projection := &externalResultProjectionFake{}
	consumer, err := streamadapter.NewExternalInteractionResultConsumer(
		transport,
		projection,
		newMemoryFailureStore(),
		"external-result-test",
		nil,
	)
	if err != nil {
		t.Fatalf("consumer: %v", err)
	}
	providerRequestDigest := canonicalFixtureDigest(
		"attempt-1",
		"incoming-call-request-1",
		"apns_voip",
	)
	fields := map[string]string{
		"eventType":             "ExternalInteractionResultReported",
		"eventId":               "attempt-1",
		"attemptId":             "attempt-1",
		"requestId":             "incoming-call-request-1",
		"operation":             "push_delivery.send",
		"status":                "sent_unconfirmed",
		"provider":              "apns_voip",
		"providerRequestDigest": providerRequestDigest,
		"recoveryAction":        "none",
		"occurredAt":            time.Now().UTC().Format(time.RFC3339Nano),
	}
	for index := 0; index < 2; index++ {
		if _, err := redis.XAdd(ctx, streamadapter.ExternalInteractionResultStream, fields); err != nil {
			t.Fatalf("append result: %v", err)
		}
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 2 {
		t.Fatalf("process results count=%d err=%v", count, err)
	}
	projection.mu.Lock()
	defer projection.mu.Unlock()
	if len(projection.byAttempt) != 1 {
		t.Fatalf("owned receipts=%d want=1", len(projection.byAttempt))
	}
	receipt := projection.byAttempt["attempt-1"]
	if receipt.ProviderRequestDigest != providerRequestDigest {
		t.Fatalf("provider digest drifted: %#v", receipt)
	}
}

func TestExternalInteractionResultConsumerRejectsTerminalDeliveryClaim(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatalf("message transport: %v", err)
	}
	projection := &externalResultProjectionFake{}
	consumer, err := streamadapter.NewExternalInteractionResultConsumer(
		transport,
		projection,
		newMemoryFailureStore(),
		"external-result-status-test",
		nil,
	)
	if err != nil {
		t.Fatalf("consumer: %v", err)
	}
	if _, err := redis.XAdd(ctx, streamadapter.ExternalInteractionResultStream, map[string]string{
		"eventType": "ExternalInteractionResultReported",
		"eventId":   "attempt-terminal-claim",
		"attemptId": "attempt-terminal-claim",
		"requestId": "incoming-call-request-terminal",
		"operation": "push_delivery.send",
		"status":    "delivered",
		"provider":  "apns_voip",
		"providerRequestDigest": canonicalFixtureDigest(
			"attempt-terminal-claim",
			"incoming-call-request-terminal",
			"apns_voip",
		),
		"recoveryAction": "none",
		"occurredAt":     time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("append terminal claim: %v", err)
	}
	if _, err := consumer.ProcessOnce(ctx); err == nil {
		t.Fatal("provider result claiming terminal delivery must be rejected")
	}
	projection.mu.Lock()
	defer projection.mu.Unlock()
	if len(projection.byAttempt) != 0 {
		t.Fatalf("terminal delivery claim reached projection: %#v", projection.byAttempt)
	}
}

func canonicalFixtureDigest(parts ...string) string {
	normalized := make([]string, 0, len(parts))
	for _, part := range parts {
		normalized = append(normalized, strings.TrimSpace(part))
	}
	sum := sha256.Sum256([]byte(strings.Join(normalized, "\x00")))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func TestExternalInteractionResultConsumerHoldsAndReleasesPersistedDeadLetter(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatalf("message transport: %v", err)
	}
	failures := newMemoryFailureStore()
	consumer, err := streamadapter.NewExternalInteractionResultConsumer(
		transport,
		&externalResultProjectionFake{},
		failures,
		"external-result-dead-letter-test",
		nil,
	)
	if err != nil {
		t.Fatalf("consumer: %v", err)
	}
	messageID, err := redis.XAdd(ctx, streamadapter.ExternalInteractionResultStream, map[string]string{
		"eventType": "ExternalInteractionResultReported",
	})
	if err != nil {
		t.Fatalf("append pre-dead-lettered result: %v", err)
	}
	if err := failures.MarkInteractionDeadLettered(
		ctx,
		streamadapter.ExternalInteractionResultStream,
		messageID,
	); err != nil {
		t.Fatalf("mark pre-dead-lettered source: %v", err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("process pre-dead-lettered result=%d err=%v", processed, err)
	}
	pending, err := redis.XPendingCount(
		ctx,
		streamadapter.ExternalInteractionResultStream,
		"notification-external-interaction-result",
	)
	if err != nil {
		t.Fatalf("inspect pending dead letter: %v", err)
	}
	if pending != 1 {
		t.Fatalf("persisted dead letter source PEL must stay held: %d", pending)
	}
	if err := consumer.RecoverDeadLetter(ctx, messageID); err != nil {
		t.Fatalf("recover held source PEL: %v", err)
	}
	held, err := failures.IsInteractionDeadLettered(
		ctx,
		streamadapter.ExternalInteractionResultStream,
		messageID,
	)
	if err != nil {
		t.Fatalf("inspect released dead letter: %v", err)
	}
	if held {
		t.Fatal("recovery did not release held source PEL")
	}
}
