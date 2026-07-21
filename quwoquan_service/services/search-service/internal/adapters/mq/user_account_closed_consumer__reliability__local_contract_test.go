package mq

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/search-service/internal/application"
)

type projectionStub struct {
	mu       sync.Mutex
	failure  error
	digests  map[string]string
	applied  int
	attempts int
}

func newProjectionStub() *projectionStub {
	return &projectionStub{digests: make(map[string]string)}
}

func (stub *projectionStub) ApplyUserAccountClosed(
	_ context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	stub.mu.Lock()
	defer stub.mu.Unlock()
	stub.attempts++
	if stub.failure != nil {
		return application.UserAccountClosedProjectionResult{}, stub.failure
	}
	if digest, exists := stub.digests[event.EventID]; exists {
		if digest != event.Digest() {
			return application.UserAccountClosedProjectionResult{},
				application.ErrUserAccountClosedEventIDConflict
		}
		return application.UserAccountClosedProjectionResult{Replayed: true}, nil
	}
	stub.digests[event.EventID] = event.Digest()
	stub.applied++
	return application.UserAccountClosedProjectionResult{}, nil
}

func (stub *projectionStub) setFailure(err error) {
	stub.mu.Lock()
	defer stub.mu.Unlock()
	stub.failure = err
}

type failureStoreStub struct {
	mu       sync.Mutex
	attempts map[string]int64
}

func newFailureStoreStub() *failureStoreStub {
	return &failureStoreStub{attempts: make(map[string]int64)}
}

func (store *failureStoreStub) RecordUserAccountClosedFailure(
	_ context.Context,
	stream string,
	messageID string,
	_ string,
	_ error,
) (int64, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	key := stream + "\x00" + messageID
	store.attempts[key]++
	return store.attempts[key], nil
}

func (store *failureStoreStub) ClearUserAccountClosedFailure(
	_ context.Context,
	stream string,
	messageID string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	delete(store.attempts, stream+"\x00"+messageID)
	return nil
}

type recordingRedis struct {
	rtredis.Client
	mu          sync.Mutex
	expireCalls map[string]time.Duration
}

func newRecordingRedis() *recordingRedis {
	return &recordingRedis{
		Client:      rtredis.NewMemoryClient(),
		expireCalls: make(map[string]time.Duration),
	}
}

func (client *recordingRedis) Expire(
	ctx context.Context,
	key string,
	ttl time.Duration,
) error {
	client.mu.Lock()
	client.expireCalls[key] = ttl
	client.mu.Unlock()
	return client.Client.Expire(ctx, key, ttl)
}

func newConsumerFixture(
	t *testing.T,
	projection *projectionStub,
	maxAttempts int64,
) (*UserAccountClosedConsumer, *recordingRedis) {
	t.Helper()
	client := newRecordingRedis()
	config := DefaultUserAccountClosedConsumerConfig()
	config.MinIdle = 0
	config.MaxAttempts = maxAttempts
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatalf("create message transport: %v", err)
	}
	consumer, err := NewUserAccountClosedConsumer(
		transport,
		projection,
		newFailureStoreStub(),
		"search-account-closure-test",
		nil,
		config,
	)
	if err != nil {
		t.Fatal(err)
	}
	return consumer, client
}

func appendAccountClosedEvent(
	t *testing.T,
	client rtredis.Client,
	eventID string,
	personaIDs []string,
) {
	t.Helper()
	now := time.Date(2026, time.July, 20, 12, 0, 0, 0, time.UTC)
	payload, err := json.Marshal(map[string]any{
		"userId":       "account-closed",
		"personaIds":   personaIDs,
		"accountState": "closed",
		"updatedAt":    now.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.XAdd(
		context.Background(),
		UserAccountEventStream,
		map[string]string{
			"eventId":        eventID,
			"eventName":      application.UserAccountClosedEventName,
			"accountId":      "account-closed",
			"accountVersion": "7",
			"payload":        string(payload),
			"occurredAt":     now.Format(time.RFC3339Nano),
		},
	); err != nil {
		t.Fatal(err)
	}
}

func pendingMessages(
	t *testing.T,
	client rtredis.Client,
) []rtredis.StreamMessage {
	t.Helper()
	messages, _, err := client.XAutoClaim(
		context.Background(),
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		"pending-inspector",
		0,
		"0-0",
		20,
	)
	if err != nil {
		t.Fatal(err)
	}
	return messages
}

func TestUserAccountClosedConsumerAppliesReplayAndAcknowledges(
	t *testing.T,
) {
	projection := newProjectionStub()
	consumer, client := newConsumerFixture(t, projection, 3)
	appendAccountClosedEvent(
		t,
		client,
		"search-account-closed-replay",
		[]string{"persona-a", "persona-b"},
	)
	appendAccountClosedEvent(
		t,
		client,
		"search-account-closed-replay",
		[]string{"persona-b", "persona-a"},
	)

	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if processed != 2 || projection.applied != 1 || projection.attempts != 2 {
		t.Fatalf(
			"processed=%d applied=%d attempts=%d",
			processed,
			projection.applied,
			projection.attempts,
		)
	}
	if pending := pendingMessages(t, client); len(pending) != 0 {
		t.Fatalf("successful replay left %d pending messages", len(pending))
	}
}

func TestUserAccountClosedConsumerRetriesThenRecovers(
	t *testing.T,
) {
	projection := newProjectionStub()
	projection.setFailure(errors.New("temporary MongoDB outage"))
	consumer, client := newConsumerFixture(t, projection, 3)
	appendAccountClosedEvent(
		t,
		client,
		"search-account-closed-recover",
		[]string{"persona-recover"},
	)

	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("transient failure must remain pending")
	}
	if pending := pendingMessages(t, client); len(pending) != 1 {
		t.Fatalf("pending after failure=%d want=1", len(pending))
	}
	projection.setFailure(nil)
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("recover pending event: %v", err)
	}
	if pending := pendingMessages(t, client); len(pending) != 0 {
		t.Fatalf("pending after recovery=%d want=0", len(pending))
	}
}

func TestUserAccountClosedConsumerDeadLettersAfterBoundedRetries(
	t *testing.T,
) {
	projection := newProjectionStub()
	projection.setFailure(errors.New("permanent projection failure with private detail"))
	consumer, client := newConsumerFixture(t, projection, 2)
	appendAccountClosedEvent(
		t,
		client,
		"search-account-closed-dlq",
		[]string{"persona-dlq"},
	)

	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("first failure must remain pending")
	}
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("second failure should dead-letter: %v", err)
	}
	if pending := pendingMessages(t, client); len(pending) != 0 {
		t.Fatalf("dead-lettered source pending=%d want=0", len(pending))
	}
	client.mu.Lock()
	ttl := client.expireCalls[UserAccountClosedDeadLetterStream]
	client.mu.Unlock()
	if ttl != 7*24*time.Hour {
		t.Fatalf("DLQ ttl=%s want=%s", ttl, 7*24*time.Hour)
	}
	if err := client.XGroupCreateMkStream(
		context.Background(),
		UserAccountClosedDeadLetterStream,
		"search-account-closure-dlq-observer",
		"0",
	); err != nil {
		t.Fatal(err)
	}
	deadLetters, err := client.XReadGroup(
		context.Background(),
		"search-account-closure-dlq-observer",
		"observer",
		map[string]string{UserAccountClosedDeadLetterStream: ">"},
		10,
		10*time.Millisecond,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(deadLetters) != 1 ||
		deadLetters[0].Values["payload"] == "" ||
		deadLetters[0].Values["errorDigest"] == "" ||
		deadLetters[0].Values["attempts"] != "2" {
		t.Fatalf("DLQ recovery envelope is incomplete: %v", deadLetters)
	}
	if _, exists := deadLetters[0].Values["error"]; exists {
		t.Fatal("DLQ must not persist raw error text")
	}
}
