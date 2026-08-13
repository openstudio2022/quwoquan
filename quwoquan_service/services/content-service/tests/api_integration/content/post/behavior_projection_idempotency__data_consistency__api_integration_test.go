package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

// TestBehaviorEventIdempotencyIndexExcludesEmptyClientEventIDs verifies only
// ContentBehaviorFact's authoritative append semantics. Recommendation-owned
// feature/candidate checkpointing is covered by Recommendation object tests.
func TestBehaviorEventIdempotencyIndexExcludesEmptyClientEventIDs(t *testing.T) {
	ctx := t.Context()
	if mongoClient == nil {
		t.Fatal("content-service tests require mongoClient")
	}
	db := mongoClient.Database("content_behavior_event_index_current")
	t.Cleanup(func() {
		if err := db.Drop(context.Background()); err != nil {
			t.Errorf("drop behavior event index database: %v", err)
		}
	})
	events := db.Collection("rm_behavior_events")

	store := behaviorpersistence.NewMongoBehaviorEventStore(db, nilLogger())
	cursor, err := events.Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list migrated behavior event indexes: %v", err)
	}
	defer cursor.Close(ctx)
	var indexes []bson.M
	if err := cursor.All(ctx, &indexes); err != nil {
		t.Fatalf("decode migrated behavior event indexes: %v", err)
	}
	var idempotencyIndex bson.M
	for _, index := range indexes {
		if index["name"] == "uq_behavior_events_actor_client_event" {
			idempotencyIndex = index
			break
		}
	}
	if idempotencyIndex == nil {
		t.Fatal("behavior event idempotency index was not created")
	}
	if unique, ok := idempotencyIndex["unique"].(bool); !ok || !unique {
		t.Fatalf("behavior event idempotency index must stay unique: %#v", idempotencyIndex)
	}
	partial, ok := bsonDocumentToMap(idempotencyIndex["partialFilterExpression"])
	if !ok {
		t.Fatalf("behavior event idempotency index must use partial filter: %#v", idempotencyIndex)
	}
	clientEventID, ok := bsonDocumentToMap(partial["clientEventId"])
	if !ok || clientEventID["$type"] != "string" || clientEventID["$gt"] != "" {
		t.Fatalf("unexpected clientEventId partial filter: %#v", partial)
	}

	if _, err := events.InsertMany(ctx, []any{
		bson.M{"_id": "missing-client-event-id", "userId": "anonymous-event-user"},
		bson.M{
			"_id": "empty-client-event-id", "userId": "anonymous-event-user",
			"clientEventId": "",
		},
	}); err != nil {
		t.Fatalf("events without an idempotency key must remain writable: %v", err)
	}
	event := ports.RawBehaviorEvent{
		ClientEventID: "event-replay",
		UserID:        "replay-user",
		SessionID:     "session",
		ContentID:     "post",
		Action:        "click",
		OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
		CreatedAt:     time.Now().UTC(),
	}
	if err := store.InsertBatch(ctx, []ports.RawBehaviorEvent{event}); err != nil {
		t.Fatalf("insert initial behavior event: %v", err)
	}
	if err := store.InsertBatch(ctx, []ports.RawBehaviorEvent{event}); err != nil {
		t.Fatalf("replay behavior event must be idempotent: %v", err)
	}
	count, err := events.CountDocuments(ctx, bson.M{
		"userId":        event.UserID,
		"clientEventId": event.ClientEventID,
	})
	if err != nil {
		t.Fatalf("count replayed behavior events: %v", err)
	}
	if count != 1 {
		t.Fatalf("replayed behavior event count=%d, want 1", count)
	}
}

func bsonDocumentToMap(value any) (bson.M, bool) {
	switch document := value.(type) {
	case bson.M:
		return document, true
	case bson.D:
		result := make(bson.M, len(document))
		for _, element := range document {
			result[element.Key] = element.Value
		}
		return result, true
	default:
		return nil, false
	}
}
