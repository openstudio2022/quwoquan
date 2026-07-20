package accountclosure

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"slices"
	"strings"
	"sync"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/search/es"
)

func TestProcessorCompletesCleanupAndReplaysIdempotently(t *testing.T) {
	t.Parallel()
	event := accountClosedEventForTest("evt-processor-normal")
	document := SearchDocumentID{
		ObjectType: contentPostSearchObjectType,
		ObjectID:   "post-closed",
	}
	store := newProcessorStoreForTest(document)
	search := &searchDeleterForTest{}
	cache := &cacheCleanerForTest{}
	processor, err := NewProcessor(store, cache, search)
	if err != nil {
		t.Fatal(err)
	}

	result, err := processor.Apply(t.Context(), event)
	if err != nil {
		t.Fatalf("apply cleanup: %v", err)
	}
	if result.Replayed {
		t.Fatal("first cleanup must not be reported as replay")
	}
	if !store.state.Completed ||
		store.completeCalls != 1 ||
		store.registerCalls != 1 {
		t.Fatalf(
			"cleanup was not completed behind tombstone: state=%+v complete=%d register=%d",
			store.state,
			store.completeCalls,
			store.registerCalls,
		)
	}
	if got := search.deleted; !slices.Equal(got, []string{document.CanonicalID()}) {
		t.Fatalf("search deletes=%v, want %s", got, document.CanonicalID())
	}

	result, err = processor.Apply(t.Context(), event)
	if err != nil {
		t.Fatalf("replay cleanup: %v", err)
	}
	if !result.Replayed {
		t.Fatal("completed inbox replay must be reported")
	}
	if store.completeCalls != 1 ||
		store.registerCalls != 1 ||
		len(search.deleted) != 1 {
		t.Fatalf(
			"replay repeated side effects: completeCalls=%d registerCalls=%d searchDeletes=%d",
			store.completeCalls,
			store.registerCalls,
			len(search.deleted),
		)
	}
}

func TestProcessorSearchFailureRemainsPendingAndRecovers(t *testing.T) {
	t.Parallel()
	event := accountClosedEventForTest("evt-processor-search-retry")
	document := SearchDocumentID{
		ObjectType: contentPostSearchObjectType,
		ObjectID:   "post-search-retry",
	}
	store := newProcessorStoreForTest(document)
	search := &searchDeleterForTest{failuresRemaining: 1}
	processor, err := NewProcessor(store, &cacheCleanerForTest{}, search)
	if err != nil {
		t.Fatal(err)
	}

	if _, err := processor.Apply(t.Context(), event); err == nil {
		t.Fatal("search deletion failure must fail the event")
	}
	if store.state.Completed || len(store.pending) != 1 {
		t.Fatalf("search failure completed inbox or consumed work: state=%+v pending=%v", store.state, store.pending)
	}

	result, err := processor.Apply(t.Context(), event)
	if err != nil {
		t.Fatalf("recover search deletion: %v", err)
	}
	if !result.Replayed {
		t.Fatal("Mongo-applied retry must be identified as replay/resume")
	}
	if !store.state.Completed || len(store.pending) != 0 {
		t.Fatalf("recovered cleanup did not converge: state=%+v pending=%v", store.state, store.pending)
	}
}

func TestConsumerFailureRetriesWithoutAcknowledgement(t *testing.T) {
	t.Parallel()
	redis := newRecordingRedisForTest()
	failures := newFailureStoreForTest()
	processor := &eventProcessorForTest{failuresRemaining: 1}
	consumer := newConsumerForTest(t, redis, processor, failures, 3)
	messageID := appendAccountClosedMessageForTest(t, redis, "evt-consumer-retry")

	if _, err := consumer.ProcessOnce(t.Context()); err == nil {
		t.Fatal("first failed attempt must be returned")
	}
	if slices.Contains(redis.acknowledged(), messageID) {
		t.Fatal("failed attempt was acknowledged")
	}
	pending, _, err := redis.XAutoClaim(
		t.Context(),
		UserAccountEventStream,
		ConsumerGroup,
		"assert-pending",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(pending) != 1 || pending[0].ID != messageID {
		t.Fatalf("failed message is not pending: %+v", pending)
	}

	if processed, err := consumer.ProcessOnce(t.Context()); err != nil || processed != 1 {
		t.Fatalf("retry did not recover: processed=%d err=%v", processed, err)
	}
	if !slices.Contains(redis.acknowledged(), messageID) {
		t.Fatal("successful retry was not acknowledged")
	}
}

func TestConsumerMovesBoundedFailureToSanitizedDLQ(t *testing.T) {
	t.Parallel()
	redis := newRecordingRedisForTest()
	failures := newFailureStoreForTest()
	processor := &eventProcessorForTest{
		failuresRemaining: 10,
		failure:           errors.New("permanent processing failure"),
	}
	consumer := newConsumerForTest(t, redis, processor, failures, 2)
	messageID := appendAccountClosedMessageForTest(t, redis, "evt-consumer-dlq")

	if _, err := consumer.ProcessOnce(t.Context()); err == nil {
		t.Fatal("first permanent failure must remain pending")
	}
	processed, err := consumer.ProcessOnce(t.Context())
	if err != nil {
		t.Fatalf("terminal retry must move to DLQ: %v", err)
	}
	if processed != 1 || !slices.Contains(redis.acknowledged(), messageID) {
		t.Fatalf("DLQ transition did not ACK source: processed=%d acked=%v", processed, redis.acknowledged())
	}
	if got := redis.expiration(DeadLetterStream); got != deadLetterRetention {
		t.Fatalf("DLQ retention=%s, want %s", got, deadLetterRetention)
	}

	if err := redis.XGroupCreateMkStream(t.Context(), DeadLetterStream, "dlq-assertion", "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := redis.XReadGroup(
		t.Context(),
		"dlq-assertion",
		"assertion",
		map[string]string{DeadLetterStream: ">"},
		10,
		0,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(messages) != 1 {
		t.Fatalf("DLQ messages=%d, want 1", len(messages))
	}
	values := messages[0].Values
	for _, forbidden := range []string{"payload", "accountId", "userId", "personaIds"} {
		if _, exists := values[forbidden]; exists {
			t.Fatalf("DLQ leaked %s: %+v", forbidden, values)
		}
	}
	for _, required := range []string{
		"deadLetterId",
		"eventIdDigest",
		"payloadDigest",
		"errorDigest",
		"attempts",
	} {
		if values[required] == "" {
			t.Fatalf("DLQ missing %s: %+v", required, values)
		}
	}
}

func TestEventDigestRejectsEventIDReuseWithDifferentPayload(t *testing.T) {
	t.Parallel()
	original := accountClosedEventForTest("evt-reused")
	reused := original
	reused.Payload.PersonaIDs = []string{"different-persona"}
	if original.Digest() == reused.Digest() {
		t.Fatal("different event data produced the same inbox digest")
	}
}

func accountClosureDigestorForTest(t *testing.T) SubjectDigestor {
	t.Helper()
	digestor, err := NewHMACSubjectDigestor(
		"account-closure-local-contract-secret",
	)
	if err != nil {
		t.Fatal(err)
	}
	return digestor
}

func TestSearchIndexerDeleterUsesCanonicalIdentityAndPropagatesFailure(t *testing.T) {
	t.Parallel()
	document := SearchDocumentID{
		ObjectType: contentPostSearchObjectType,
		ObjectID:   "post-search-adapter",
	}
	writer := &searchWriterForTest{}
	deleter, err := NewSearchIndexerDeleter(es.NewIndexer(writer, "search_objects"), true)
	if err != nil {
		t.Fatal(err)
	}
	if err := deleter.DeleteSearchDocument(t.Context(), document); err != nil {
		t.Fatalf("delete canonical document: %v", err)
	}
	if !slices.Equal(writer.deleted, []string{document.CanonicalID()}) {
		t.Fatalf("deleted ids=%v, want %s", writer.deleted, document.CanonicalID())
	}

	writer.failure = errors.New("search backend unavailable")
	if err := deleter.DeleteSearchDocument(t.Context(), document); err == nil {
		t.Fatal("search backend failure was swallowed")
	}
	if _, err := NewSearchIndexerDeleter(nil, true); err == nil {
		t.Fatal("enabled search accepted a missing indexer")
	}
}

func TestRedisPersonalDataCacheCleanerDeletesRoutedKeys(t *testing.T) {
	t.Parallel()
	client := rtredis.NewMemoryClient()
	router := redisKeyRouterForTest{client: client}
	digestor := accountClosureDigestorForTest(t)
	cleaner, err := NewRedisPersonalDataCacheCleaner(router, digestor)
	if err != nil {
		t.Fatal(err)
	}
	keys := []string{
		"rec:negative:{account-closed}",
		"rec:session_signals:{account-closed}:session-1",
		"ix:watermark:{account-closed}",
	}
	for _, key := range keys {
		if err := client.Set(t.Context(), key, "personal", time.Hour); err != nil {
			t.Fatal(err)
		}
	}
	if err := cleaner.DeletePersonalCacheKeys(t.Context(), keys); err != nil {
		t.Fatal(err)
	}
	for _, key := range keys {
		if _, err := client.Get(t.Context(), key); !errors.Is(err, rtredis.ErrKeyNotFound) {
			t.Fatalf("personal cache key %q remains: %v", key, err)
		}
	}
	if err := cleaner.BlockClosedSubjects(
		t.Context(),
		[]string{"account-closed"},
	); err != nil {
		t.Fatal(err)
	}
	closed, err := cleaner.IsSubjectClosed(t.Context(), "account-closed")
	if err != nil || !closed {
		t.Fatalf("closed subject guard=%v err=%v", closed, err)
	}
	tombstoneKey, err := closedSubjectRedisKey(digestor, "account-closed")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(tombstoneKey, "account-closed") {
		t.Fatalf("closed subject Redis key leaked identity: %q", tombstoneKey)
	}
}

type processorStoreForTest struct {
	mu            sync.Mutex
	state         CleanupState
	pending       []SearchDocumentID
	prepareCalls  int
	completeCalls int
	registerCalls int
}

func (store *processorStoreForTest) RegisterClosedSubjects(
	context.Context,
	UserAccountClosedEvent,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.registerCalls++
	return nil
}

func (store *processorStoreForTest) PersonalCacheKeys(
	context.Context,
	UserAccountClosedEvent,
) ([]string, error) {
	return []string{"rec:negative:{account-closed}"}, nil
}

func newProcessorStoreForTest(documents ...SearchDocumentID) *processorStoreForTest {
	return &processorStoreForTest{
		state:   CleanupState{MongoApplied: true},
		pending: append([]SearchDocumentID(nil), documents...),
	}
}

func (store *processorStoreForTest) ReserveCleanup(
	_ context.Context,
	_ UserAccountClosedEvent,
) (CleanupState, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.state, nil
}

func (store *processorStoreForTest) PrepareCleanup(
	context.Context,
	UserAccountClosedEvent,
) (CleanupState, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.prepareCalls++
	store.state.AlreadyApplied = store.prepareCalls > 1
	return store.state, nil
}

func (store *processorStoreForTest) PendingSearchDocuments(
	context.Context,
	string,
	int64,
) ([]SearchDocumentID, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return append([]SearchDocumentID(nil), store.pending...), nil
}

func (store *processorStoreForTest) MarkSearchDocumentDone(
	_ context.Context,
	_ string,
	document SearchDocumentID,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	for index, pending := range store.pending {
		if pending.CanonicalID() == document.CanonicalID() {
			store.pending = append(store.pending[:index], store.pending[index+1:]...)
			return nil
		}
	}
	return errors.New("search work missing")
}

func (store *processorStoreForTest) MarkCompleted(
	context.Context,
	UserAccountClosedEvent,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if len(store.pending) != 0 {
		return errors.New("search work remains")
	}
	store.state.Completed = true
	store.completeCalls++
	return nil
}

type searchDeleterForTest struct {
	mu                sync.Mutex
	failuresRemaining int
	deleted           []string
}

type cacheCleanerForTest struct {
	mu      sync.Mutex
	deleted []string
	blocked []string
}

func (cleaner *cacheCleanerForTest) BlockClosedSubjects(
	_ context.Context,
	subjectIDs []string,
) error {
	cleaner.mu.Lock()
	defer cleaner.mu.Unlock()
	cleaner.blocked = append(cleaner.blocked, subjectIDs...)
	return nil
}

func (cleaner *cacheCleanerForTest) DeletePersonalCacheKeys(
	_ context.Context,
	keys []string,
) error {
	cleaner.mu.Lock()
	defer cleaner.mu.Unlock()
	cleaner.deleted = append(cleaner.deleted, keys...)
	return nil
}

type searchWriterForTest struct {
	deleted []string
	failure error
}

func (writer *searchWriterForTest) Upsert(
	context.Context,
	string,
	string,
	map[string]any,
) error {
	return nil
}

func (writer *searchWriterForTest) Delete(
	_ context.Context,
	_ string,
	id string,
) error {
	if writer.failure != nil {
		return writer.failure
	}
	writer.deleted = append(writer.deleted, id)
	return nil
}

func (deleter *searchDeleterForTest) DeleteSearchDocument(
	_ context.Context,
	document SearchDocumentID,
) error {
	deleter.mu.Lock()
	defer deleter.mu.Unlock()
	if deleter.failuresRemaining > 0 {
		deleter.failuresRemaining--
		return errors.New("search unavailable")
	}
	deleter.deleted = append(deleter.deleted, document.CanonicalID())
	return nil
}

type eventProcessorForTest struct {
	mu                sync.Mutex
	failuresRemaining int
	failure           error
}

func (processor *eventProcessorForTest) Apply(
	context.Context,
	UserAccountClosedEvent,
) (ApplyResult, error) {
	processor.mu.Lock()
	defer processor.mu.Unlock()
	if processor.failuresRemaining > 0 {
		processor.failuresRemaining--
		if processor.failure != nil {
			return ApplyResult{}, processor.failure
		}
		return ApplyResult{}, errors.New("transient processing failure")
	}
	return ApplyResult{}, nil
}

type failureStoreForTest struct {
	mu       sync.Mutex
	attempts map[string]int64
}

func newFailureStoreForTest() *failureStoreForTest {
	return &failureStoreForTest{attempts: map[string]int64{}}
}

func (store *failureStoreForTest) RecordFailure(
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

func (store *failureStoreForTest) ClearFailure(
	_ context.Context,
	stream string,
	messageID string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	delete(store.attempts, stream+"\x00"+messageID)
	return nil
}

type recordingRedisForTest struct {
	rtredis.Client
	mu          sync.Mutex
	acks        []string
	expirations map[string]time.Duration
}

type redisKeyRouterForTest struct {
	client rtredis.Client
}

func (router redisKeyRouterForTest) ForKey(string) rtredis.Client {
	return router.client
}

func newRecordingRedisForTest() *recordingRedisForTest {
	return &recordingRedisForTest{
		Client:      rtredis.NewMemoryClient(),
		expirations: map[string]time.Duration{},
	}
}

func (redis *recordingRedisForTest) XAck(
	ctx context.Context,
	stream string,
	group string,
	ids ...string,
) error {
	if err := redis.Client.XAck(ctx, stream, group, ids...); err != nil {
		return err
	}
	redis.mu.Lock()
	defer redis.mu.Unlock()
	redis.acks = append(redis.acks, ids...)
	return nil
}

func (redis *recordingRedisForTest) Expire(
	ctx context.Context,
	key string,
	ttl time.Duration,
) error {
	if err := redis.Client.Expire(ctx, key, ttl); err != nil {
		return err
	}
	redis.mu.Lock()
	defer redis.mu.Unlock()
	redis.expirations[key] = ttl
	return nil
}

func (redis *recordingRedisForTest) acknowledged() []string {
	redis.mu.Lock()
	defer redis.mu.Unlock()
	return append([]string(nil), redis.acks...)
}

func (redis *recordingRedisForTest) expiration(key string) time.Duration {
	redis.mu.Lock()
	defer redis.mu.Unlock()
	return redis.expirations[key]
}

func newConsumerForTest(
	t *testing.T,
	redis rtredis.Client,
	processor EventProcessor,
	failures FailureStore,
	maxAttempts int64,
) *Consumer {
	t.Helper()
	consumer, err := NewConsumer(
		redis,
		processor,
		failures,
		"local-contract-consumer",
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		ConsumerConfig{
			BatchSize:    10,
			MaxAttempts:  maxAttempts,
			MinIdle:      0,
			PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	return consumer
}

func appendAccountClosedMessageForTest(
	t *testing.T,
	redis rtredis.Client,
	eventID string,
) string {
	t.Helper()
	event := accountClosedEventForTest(eventID)
	payload, err := json.Marshal(map[string]any{
		"userId":       event.Payload.UserID,
		"personaIds":   event.Payload.PersonaIDs,
		"accountState": event.Payload.AccountState,
		"updatedAt":    event.Payload.UpdatedAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	messageID, err := redis.XAdd(t.Context(), UserAccountEventStream, map[string]string{
		"eventId":        event.EventID,
		"eventName":      event.EventName,
		"accountId":      event.AccountID,
		"accountVersion": "1",
		"payload":        string(payload),
		"occurredAt":     event.OccurredAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	return messageID
}

func accountClosedEventForTest(eventID string) UserAccountClosedEvent {
	occurredAt := time.Date(2026, 7, 20, 8, 0, 0, 0, time.UTC)
	return UserAccountClosedEvent{
		EventID:        eventID,
		EventName:      UserAccountClosedName,
		AccountID:      "account-closed",
		AccountVersion: 1,
		Payload: UserAccountClosedPayload{
			UserID:       "account-closed",
			PersonaIDs:   []string{"persona-closed"},
			AccountState: "closed",
			UpdatedAt:    occurredAt,
		},
		OccurredAt: occurredAt,
	}
}
