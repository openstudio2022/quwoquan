// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
package api_integration

import (
	"context"
	"errors"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	feedbackapplication "quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
	"quwoquan_service/services/search-service/internal/search/search_feedback_fact/infrastructure/feedbackstore"
	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
)

func newFeedbackStore(t *testing.T) *feedbackstore.Store {
	t.Helper()
	store := feedbackstore.NewStore(mongoDB)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure search feedback indexes: %v", err)
	}
	return store
}

type retryingFeedbackSignalPublisher struct {
	fail    bool
	signals []signalapplication.Signal
}

type feedbackSignalObserver struct {
	outcomes   []string
	pendingAge float64
}

func (observer *feedbackSignalObserver) ObserveFeedbackSignalRelay(
	outcome string,
) {
	observer.outcomes = append(observer.outcomes, outcome)
}

func (observer *feedbackSignalObserver) SetFeedbackSignalPendingAge(
	seconds float64,
) {
	observer.pendingAge = seconds
}

func (publisher *retryingFeedbackSignalPublisher) PublishSearchSignal(
	_ context.Context,
	signal signalapplication.Signal,
) error {
	publisher.signals = append(publisher.signals, signal)
	if publisher.fail {
		return errors.New("redis unavailable")
	}
	return nil
}

func TestFeedbackRecordDedupesFactAndCompletesEveryAcceptedKey(t *testing.T) {
	cleanFeedbackCollections(t)
	store := newFeedbackStore(t)
	ctx := context.Background()
	event := feedbackapplication.Event{
		SearchRequestID: "req-dedupe-1",
		ViewerID:        "persona-feedback-owner",
		EventType:       "click",
		ObjectID:        "post-1",
		Target:          "article",
		RankPosition:    3,
		ReferralSource:  "searchResults",
	}
	for _, meta := range []feedbackapplication.CommandMeta{
		{IdempotencyKey: "feedback-key-1", CommandDigest: "digest-1"},
		{IdempotencyKey: "feedback-key-1", CommandDigest: "digest-1"},
		{IdempotencyKey: "feedback-key-1-retry", CommandDigest: "digest-1"},
	} {
		if err := store.Record(ctx, event, meta); err != nil {
			t.Fatalf("record replay: %v", err)
		}
	}
	factCount, err := mongoDB.Collection("search_feedback_events").CountDocuments(
		ctx,
		bson.M{"searchRequestId": event.SearchRequestID},
	)
	if err != nil || factCount != 1 {
		t.Fatalf("semantic dedupe count=%d err=%v", factCount, err)
	}
	receiptCount, err := mongoDB.Collection(
		"search_feedback_command_receipts",
	).CountDocuments(ctx, bson.M{
		"_id": bson.M{"$in": []string{
			"feedback-key-1",
			"feedback-key-1-retry",
		}},
		"status": "completed",
	})
	if err != nil || receiptCount != 2 {
		t.Fatalf("completed receipt count=%d err=%v", receiptCount, err)
	}
}

func TestFeedbackRecordCommitsFactReceiptAndDeliveryAtomically(t *testing.T) {
	cleanFeedbackCollections(t)
	store := newFeedbackStore(t)
	ctx := context.Background()
	event := feedbackapplication.Event{
		SearchRequestID: "req-atomic-delivery",
		ViewerID:        "persona-atomic-owner",
		EventType:       "click",
		ObjectID:        "post-atomic",
		Target:          "article",
		RankPosition:    1,
	}
	signal, ok := feedbackapplication.RecommendationSignal(
		event,
		time.Date(2026, time.July, 26, 0, 0, 0, 0, time.UTC),
	)
	if !ok {
		t.Fatal("test click must produce a stable signal")
	}
	if _, err := mongoDB.Collection(
		"search_feedback_signal_deliveries",
	).InsertOne(ctx, bson.M{
		"_id":               signal.SignalID,
		"feedbackFactId":    bson.NewObjectID(),
		"signalPayloadJson": "{}",
		"status":            "pending",
		"createdAt":         time.Now().UTC(),
		"updatedAt":         time.Now().UTC(),
	}); err != nil {
		t.Fatalf("seed conflicting delivery: %v", err)
	}
	err := store.Record(ctx, event, feedbackapplication.CommandMeta{
		IdempotencyKey: "atomic-delivery-key",
		CommandDigest:  "atomic-delivery-digest",
	})
	if err == nil {
		t.Fatal("conflicting delivery invariant must abort feedback transaction")
	}
	for _, collection := range []string{
		"search_feedback_events",
		"search_feedback_command_receipts",
	} {
		count, countErr := mongoDB.Collection(collection).CountDocuments(
			ctx,
			bson.M{},
		)
		if countErr != nil || count != 0 {
			t.Fatalf(
				"%s must roll back with delivery invariant error: count=%d err=%v",
				collection,
				count,
				countErr,
			)
		}
	}
}

func TestFeedbackSignalRelayRecoversCommittedClickAfterPublishFailure(
	t *testing.T,
) {
	cleanFeedbackCollections(t)
	store := newFeedbackStore(t)
	ctx := context.Background()
	event := feedbackapplication.Event{
		SearchRequestID: "req-signal-relay",
		ViewerID:        "persona-signal-owner",
		EventType:       "click",
		ObjectID:        "post-signal",
		Target:          "article",
		RankPosition:    2,
	}
	if err := store.Record(
		ctx,
		event,
		feedbackapplication.CommandMeta{
			IdempotencyKey: "feedback-signal-key",
			CommandDigest:  "feedback-signal-digest",
		},
	); err != nil {
		t.Fatal(err)
	}
	publisher := &retryingFeedbackSignalPublisher{fail: true}
	observer := &feedbackSignalObserver{}
	relay, err := feedbackstore.NewSignalRelay(
		store,
		publisher,
		observer,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if didWork, err := relay.ProcessOnce(ctx); err == nil || !didWork {
		t.Fatalf(
			"first publish must fail without acknowledging fact: didWork=%t err=%v",
			didWork,
			err,
		)
	}
	pending, err := mongoDB.Collection(
		"search_feedback_signal_deliveries",
	).CountDocuments(ctx, bson.M{
		"status": "pending",
	})
	if err != nil || pending != 1 {
		t.Fatalf("pending signal delivery was acknowledged: count=%d err=%v", pending, err)
	}
	mutatedFacts, err := mongoDB.Collection(
		"search_feedback_events",
	).CountDocuments(ctx, bson.M{
		"signalPublishedAt": bson.M{"$exists": true},
	})
	if err != nil || mutatedFacts != 0 {
		t.Fatalf("feedback fact must not contain relay state: count=%d err=%v", mutatedFacts, err)
	}
	publisher.fail = false
	if didWork, err := relay.ProcessOnce(ctx); err != nil || !didWork {
		t.Fatalf("retry must publish pending click: didWork=%t err=%v", didWork, err)
	}
	if len(publisher.signals) != 2 ||
		publisher.signals[0].SignalID != publisher.signals[1].SignalID {
		t.Fatalf("relay replay changed semantic signal: %#v", publisher.signals)
	}
	if len(observer.outcomes) != 2 ||
		observer.outcomes[0] != "publish_error" ||
		observer.outcomes[1] != "published" {
		t.Fatalf("relay outcomes=%v", observer.outcomes)
	}
	if didWork, err := relay.ProcessOnce(ctx); err != nil || didWork {
		t.Fatalf("completed click must not republish: didWork=%t err=%v", didWork, err)
	}
	published, err := mongoDB.Collection(
		"search_feedback_signal_deliveries",
	).CountDocuments(ctx, bson.M{
		"status":      "published",
		"publishedAt": bson.M{"$exists": true},
	})
	if err != nil || published != 1 {
		t.Fatalf("published signal delivery missing: count=%d err=%v", published, err)
	}
}

func TestFeedbackConflictsReserveTransportKey(t *testing.T) {
	cleanFeedbackCollections(t)
	store := newFeedbackStore(t)
	ctx := context.Background()
	event := feedbackapplication.Event{
		SearchRequestID: "req-conflict",
		ViewerID:        "persona-owner",
		EventType:       "click",
		ObjectID:        "post-1",
		Target:          "article",
		RankPosition:    1,
	}
	first := feedbackapplication.CommandMeta{
		IdempotencyKey: "feedback-key-a",
		CommandDigest:  "digest-a",
	}
	if err := store.Record(ctx, event, first); err != nil {
		t.Fatalf("first record: %v", err)
	}
	reusedKey := first
	reusedKey.CommandDigest = "digest-b"
	if err := store.Record(ctx, event, reusedKey); !errors.Is(
		err,
		feedbackapplication.ErrIdempotencyConflict,
	) {
		t.Fatalf("same key with new payload must conflict, got %v", err)
	}
	freshConflict := feedbackapplication.CommandMeta{
		IdempotencyKey: "feedback-key-b",
		CommandDigest:  "digest-b",
	}
	for attempt := 0; attempt < 2; attempt++ {
		if err := store.Record(ctx, event, freshConflict); !errors.Is(
			err,
			feedbackapplication.ErrIdempotencyConflict,
		) {
			t.Fatalf("semantic conflict attempt %d got %v", attempt+1, err)
		}
	}
	count, err := mongoDB.Collection(
		"search_feedback_command_receipts",
	).CountDocuments(ctx, bson.M{
		"_id":    freshConflict.IdempotencyKey,
		"status": "conflict",
	})
	if err != nil || count != 1 {
		t.Fatalf("conflicting key was not reserved: count=%d err=%v", count, err)
	}
}

func TestFeedbackIndexesAndRetiredFieldMigration(t *testing.T) {
	feedback := mongoDB.Collection("search_feedback_events")
	ctx := context.Background()
	if err := feedback.Drop(ctx); err != nil {
		t.Fatalf("drop feedback collection: %v", err)
	}
	if _, err := feedback.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "idempotencyKey", Value: 1}},
		Options: options.Index().
			SetUnique(true).
			SetName("uq_search_feedback_idempotency"),
	}); err != nil {
		t.Fatalf("create retired index: %v", err)
	}
	if _, err := feedback.InsertOne(ctx, bson.M{
		"searchRequestId":   "legacy-request",
		"eventType":         "click",
		"objectId":          "legacy-post",
		"idempotencyKey":    "legacy-key",
		"signalPublishedAt": time.Now().UTC(),
		"commandDigest":     "legacy-digest",
		"createdAt":         time.Now().UTC(),
	}); err != nil {
		t.Fatalf("seed retired fact shape: %v", err)
	}
	store := newFeedbackStore(t)
	_ = store
	count, err := feedback.CountDocuments(ctx, bson.M{
		"idempotencyKey": bson.M{"$exists": true},
	})
	if err != nil || count != 0 {
		t.Fatalf("retired field remains: count=%d err=%v", count, err)
	}
	count, err = feedback.CountDocuments(ctx, bson.M{
		"signalPublishedAt": bson.M{"$exists": true},
	})
	if err != nil || count != 0 {
		t.Fatalf("retired signal checkpoint remains on feedback fact: count=%d err=%v", count, err)
	}
	assertTTLIndex(
		t,
		"search_feedback_events",
		"idx_search_feedback_ttl",
		int32(feedbackstore.FeedbackTTLSeconds),
	)
	assertTTLIndex(
		t,
		"search_feedback_command_receipts",
		"idx_search_feedback_receipt_expiry",
		0,
	)
	assertTTLIndex(
		t,
		"search_feedback_signal_deliveries",
		"idx_search_feedback_signal_delivery_expiry",
		0,
	)
}

func assertTTLIndex(
	t *testing.T,
	collection string,
	indexName string,
	want int32,
) {
	t.Helper()
	cursor, err := mongoDB.Collection(collection).Indexes().List(
		context.Background(),
	)
	if err != nil {
		t.Fatalf("list %s indexes: %v", collection, err)
	}
	var indexes []bson.M
	if err := cursor.All(context.Background(), &indexes); err != nil {
		t.Fatalf("decode %s indexes: %v", collection, err)
	}
	for _, index := range indexes {
		if index["name"] != indexName {
			continue
		}
		switch value := index["expireAfterSeconds"].(type) {
		case int32:
			if value != want {
				t.Fatalf("%s TTL=%d want=%d", indexName, value, want)
			}
		case int64:
			if int32(value) != want {
				t.Fatalf("%s TTL=%d want=%d", indexName, value, want)
			}
		default:
			t.Fatalf("%s has invalid TTL: %v", indexName, index)
		}
		return
	}
	t.Fatalf("%s missing index %s", collection, indexName)
}
