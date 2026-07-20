package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	streamadapter "quwoquan_service/services/notification-service/internal/adapters/stream"
	"quwoquan_service/services/notification-service/internal/application"
)

type userAccountClosedProjectionStub struct {
	mu       sync.Mutex
	failure  error
	digests  map[string]string
	applied  int
	attempts int
}

func newUserAccountClosedProjectionStub() *userAccountClosedProjectionStub {
	return &userAccountClosedProjectionStub{
		digests: make(map[string]string),
	}
}

func (stub *userAccountClosedProjectionStub) ApplyUserAccountClosed(
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

func (stub *userAccountClosedProjectionStub) setFailure(failure error) {
	stub.mu.Lock()
	defer stub.mu.Unlock()
	stub.failure = failure
}

func (stub *userAccountClosedProjectionStub) counts() (int, int) {
	stub.mu.Lock()
	defer stub.mu.Unlock()
	return stub.applied, stub.attempts
}

type userAccountClosedFailureStoreStub struct {
	mu       sync.Mutex
	attempts map[string]int64
}

func newUserAccountClosedFailureStoreStub() *userAccountClosedFailureStoreStub {
	return &userAccountClosedFailureStoreStub{
		attempts: make(map[string]int64),
	}
}

func (store *userAccountClosedFailureStoreStub) RecordUserAccountClosedFailure(
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

func (store *userAccountClosedFailureStoreStub) ClearUserAccountClosedFailure(
	_ context.Context,
	stream string,
	messageID string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	delete(store.attempts, stream+"\x00"+messageID)
	return nil
}

type recordingUserAccountClosedRedis struct {
	rtredis.Client
	mu          sync.Mutex
	expireCalls map[string]time.Duration
}

func newRecordingUserAccountClosedRedis() *recordingUserAccountClosedRedis {
	return &recordingUserAccountClosedRedis{
		Client:      rtredis.NewMemoryClient(),
		expireCalls: make(map[string]time.Duration),
	}
}

func (client *recordingUserAccountClosedRedis) Expire(
	ctx context.Context,
	key string,
	ttl time.Duration,
) error {
	client.mu.Lock()
	client.expireCalls[key] = ttl
	client.mu.Unlock()
	return client.Client.Expire(ctx, key, ttl)
}

func (client *recordingUserAccountClosedRedis) recordedTTL(
	key string,
) time.Duration {
	client.mu.Lock()
	defer client.mu.Unlock()
	return client.expireCalls[key]
}

func newUserAccountClosedConsumerFixture(
	t *testing.T,
	projection *userAccountClosedProjectionStub,
	maxAttempts int64,
) (*streamadapter.UserAccountClosedConsumer, *recordingUserAccountClosedRedis) {
	t.Helper()
	client := newRecordingUserAccountClosedRedis()
	config := streamadapter.DefaultUserAccountClosedConsumerConfig()
	config.MinIdle = 0
	config.MaxAttempts = maxAttempts
	consumer, err := streamadapter.NewUserAccountClosedConsumer(
		client,
		projection,
		newUserAccountClosedFailureStoreStub(),
		"notification-account-closure-test",
		nil,
		config,
	)
	if err != nil {
		t.Fatalf("create UserAccountClosed consumer: %v", err)
	}
	return consumer, client
}

func appendUserAccountClosedContractEvent(
	t *testing.T,
	client rtredis.Client,
	eventID string,
	userID string,
	personaIDs []string,
) string {
	t.Helper()
	now := time.Date(2026, time.July, 20, 12, 0, 0, 0, time.UTC)
	payload, err := json.Marshal(map[string]any{
		"userId":       userID,
		"personaIds":   personaIDs,
		"accountState": "closed",
		"updatedAt":    now.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("marshal UserAccountClosed payload: %v", err)
	}
	messageID, err := client.XAdd(
		context.Background(),
		streamadapter.UserAccountEventStream,
		map[string]string{
			"eventId":        eventID,
			"eventName":      application.UserAccountClosedEventName,
			"accountId":      userID,
			"accountVersion": "7",
			"payload":        string(payload),
			"occurredAt":     now.Format(time.RFC3339Nano),
		},
	)
	if err != nil {
		t.Fatalf("append UserAccountClosed event: %v", err)
	}
	return messageID
}

func pendingUserAccountClosedMessages(
	t *testing.T,
	client rtredis.Client,
) []rtredis.StreamMessage {
	t.Helper()
	messages, _, err := client.XAutoClaim(
		context.Background(),
		streamadapter.UserAccountEventStream,
		streamadapter.UserAccountClosedConsumerGroup,
		"pending-inspector",
		0,
		"0-0",
		20,
	)
	if err != nil {
		t.Fatalf("inspect UserAccountClosed pending messages: %v", err)
	}
	return messages
}

func TestUserAccountClosedConsumerAppliesAndDeduplicatesReplay(
	t *testing.T,
) {
	projection := newUserAccountClosedProjectionStub()
	consumer, client := newUserAccountClosedConsumerFixture(
		t,
		projection,
		3,
	)
	appendUserAccountClosedContractEvent(
		t,
		client,
		"evt-account-closed-replay",
		"user-closed",
		[]string{"persona-a", "persona-b"},
	)
	appendUserAccountClosedContractEvent(
		t,
		client,
		"evt-account-closed-replay",
		"user-closed",
		[]string{"persona-b", "persona-a"},
	)

	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatalf("process UserAccountClosed replay: %v", err)
	}
	if processed != 2 {
		t.Fatalf("processed=%d want=2", processed)
	}
	applied, attempts := projection.counts()
	if applied != 1 || attempts != 2 {
		t.Fatalf(
			"projection counts applied=%d attempts=%d want=1/2",
			applied,
			attempts,
		)
	}
	if pending := pendingUserAccountClosedMessages(t, client); len(pending) != 0 {
		t.Fatalf("successful replay left %d pending messages", len(pending))
	}
}

func TestUserAccountClosedConsumerLeavesFailurePendingThenRecovers(
	t *testing.T,
) {
	projection := newUserAccountClosedProjectionStub()
	projection.setFailure(errors.New("temporary MongoDB outage"))
	consumer, client := newUserAccountClosedConsumerFixture(
		t,
		projection,
		3,
	)
	appendUserAccountClosedContractEvent(
		t,
		client,
		"evt-account-closed-recover",
		"user-recover",
		[]string{"persona-recover"},
	)

	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("transient projection failure must be returned")
	}
	if pending := pendingUserAccountClosedMessages(t, client); len(pending) != 1 {
		t.Fatalf("pending after failure=%d want=1", len(pending))
	}

	projection.setFailure(nil)
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("recover pending UserAccountClosed event: %v", err)
	}
	if pending := pendingUserAccountClosedMessages(t, client); len(pending) != 0 {
		t.Fatalf("pending after recovery=%d want=0", len(pending))
	}
	applied, _ := projection.counts()
	if applied != 1 {
		t.Fatalf("applied after recovery=%d want=1", applied)
	}
}

func TestUserAccountClosedConsumerDeadLettersAfterFiniteRetriesWithTTL(
	t *testing.T,
) {
	projection := newUserAccountClosedProjectionStub()
	projection.setFailure(errors.New("permanent projection failure"))
	consumer, client := newUserAccountClosedConsumerFixture(
		t,
		projection,
		2,
	)
	appendUserAccountClosedContractEvent(
		t,
		client,
		"evt-account-closed-dlq",
		"user-dlq",
		[]string{"persona-dlq"},
	)

	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("first projection failure must remain pending")
	}
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("second failure should dead-letter cleanly: %v", err)
	}
	if pending := pendingUserAccountClosedMessages(t, client); len(pending) != 0 {
		t.Fatalf("dead-lettered source pending=%d want=0", len(pending))
	}
	if ttl := client.recordedTTL(
		streamadapter.UserAccountClosedDeadLetterStream,
	); ttl != 7*24*time.Hour {
		t.Fatalf("DLQ ttl=%s want=%s", ttl, 7*24*time.Hour)
	}
	if err := client.XGroupCreateMkStream(
		context.Background(),
		streamadapter.UserAccountClosedDeadLetterStream,
		"notification-account-closure-dlq-observer",
		"0",
	); err != nil {
		t.Fatalf("create DLQ observer group: %v", err)
	}
	deadLetters, err := client.XReadGroup(
		context.Background(),
		"notification-account-closure-dlq-observer",
		"observer",
		map[string]string{
			streamadapter.UserAccountClosedDeadLetterStream: ">",
		},
		10,
		10*time.Millisecond,
	)
	if err != nil {
		t.Fatalf("read UserAccountClosed DLQ: %v", err)
	}
	if len(deadLetters) != 1 {
		t.Fatalf("DLQ entries=%d want=1", len(deadLetters))
	}
	if deadLetters[0].Values["payload"] == "" ||
		deadLetters[0].Values["errorDigest"] == "" ||
		deadLetters[0].Values["attempts"] != "2" {
		t.Fatalf("DLQ recovery envelope is incomplete: %v", deadLetters[0].Values)
	}
	if _, exists := deadLetters[0].Values["error"]; exists {
		t.Fatal("DLQ must not persist raw error text")
	}
}
