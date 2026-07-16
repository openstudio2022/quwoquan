package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

func TestPersonaRelationshipStreamProjectsCanonicalFollowReadModel(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	relationships := db.Collection("persona_follow_projection")
	inbox := db.Collection("persona_relationship_projection_inbox")
	cleanup := func() {
		_, _ = relationships.DeleteMany(ctx, bson.M{"sourcePersonaId": bson.M{"$regex": "^stream_"}})
		_, _ = inbox.DeleteMany(ctx, bson.M{"eventId": bson.M{"$regex": "^stream_"}})
	}
	cleanup()
	t.Cleanup(cleanup)

	projector := recinfra.NewPersonaRelationshipProjection(db)
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure persona relationship projection indexes: %v", err)
	}
	consumer := recinfra.NewPersonaRelationshipProjectionConsumer(
		requireTestRouter(t).Scene("general"), projector, "content-contract-worker", nil,
	)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("ensure relationship stream consumer group: %v", err)
	}
	now := time.Date(2026, 7, 14, 12, 0, 0, 0, time.UTC)
	stream := requireTestRouter(t).Scene("general")
	for _, event := range []map[string]string{
		{
			"eventId": "stream_follow_1", "eventName": "PersonaFollowStateChanged", "pairId": "stream_pair", "sourcePersonaId": "stream_viewer", "targetPersonaId": "stream_target", "following": "true", "version": "1", "occurredAt": now.Format(time.RFC3339Nano),
		},
		{
			"eventId": "stream_follow_2", "eventName": "PersonaFollowStateChanged", "pairId": "stream_pair", "sourcePersonaId": "stream_target", "targetPersonaId": "stream_viewer", "following": "true", "version": "2", "occurredAt": now.Add(time.Second).Format(time.RFC3339Nano),
		},
		{
			"eventId": "stream_block_3", "eventName": "PersonaBlocked", "pairId": "stream_pair", "sourcePersonaId": "stream_viewer", "targetPersonaId": "stream_target", "following": "false", "version": "3", "clearedFollowDirections": "2", "occurredAt": now.Add(2 * time.Second).Format(time.RFC3339Nano),
		},
	} {
		if _, err := stream.XAdd(ctx, recinfra.PersonaRelationshipEventStream, event); err != nil {
			t.Fatalf("append relationship stream event: %v", err)
		}
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("consume relationship stream: %v", err)
	}
	if processed != 3 {
		t.Fatalf("processed=%d want 3", processed)
	}
	for _, direction := range []struct{ source, target string }{
		{source: "stream_viewer", target: "stream_target"},
		{source: "stream_target", target: "stream_viewer"},
	} {
		var doc struct {
			Following bool  `bson:"following"`
			Version   int64 `bson:"version"`
		}
		if err := relationships.FindOne(ctx, bson.M{"sourcePersonaId": direction.source, "targetPersonaId": direction.target}).Decode(&doc); err != nil {
			t.Fatalf("read projected %s -> %s: %v", direction.source, direction.target, err)
		}
		if doc.Following || doc.Version != 3 {
			t.Fatalf("projected %s -> %s = %+v, want blocked false version 3", direction.source, direction.target, doc)
		}
	}
	count, err := inbox.CountDocuments(ctx, bson.M{"eventId": bson.M{"$regex": "^stream_"}})
	if err != nil || count != 3 {
		t.Fatalf("projection inbox count=%d err=%v want 3", count, err)
	}
}
