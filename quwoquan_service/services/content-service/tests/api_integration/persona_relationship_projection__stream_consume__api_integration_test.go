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

	// PersonaBlocked 之后：block 事实投影可被读路径判定（双向）。
	blockReader := recinfra.NewPersonaBlockReader(db)
	blocked, err := blockReader.IsBlockedBetween(ctx, "stream_viewer", "stream_target")
	if err != nil || !blocked {
		t.Fatalf("IsBlockedBetween(viewer, target)=%v err=%v want true", blocked, err)
	}
	blocked, err = blockReader.IsBlockedBetween(ctx, "stream_target", "stream_viewer")
	if err != nil || !blocked {
		t.Fatalf("IsBlockedBetween(target, viewer)=%v err=%v want true", blocked, err)
	}
	blockedPersonaIDs, err := blockReader.ListBlockedPersonaIDs(ctx, "stream_viewer")
	if err != nil ||
		len(blockedPersonaIDs) != 1 ||
		blockedPersonaIDs[0] != "stream_target" {
		t.Fatalf(
			"ListBlockedPersonaIDs(viewer)=%v err=%v want [stream_target]",
			blockedPersonaIDs,
			err,
		)
	}

	// PersonaUnblocked 之后：block 标记清除、follow 不恢复。
	if _, err := stream.XAdd(ctx, recinfra.PersonaRelationshipEventStream, map[string]string{
		"eventId": "stream_unblock_4", "eventName": "PersonaUnblocked", "pairId": "stream_pair",
		"sourcePersonaId": "stream_viewer", "targetPersonaId": "stream_target",
		"following": "false", "version": "4",
		"occurredAt": now.Add(3 * time.Second).Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("append unblock stream event: %v", err)
	}
	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("consume unblock stream: %v", err)
	}
	blocked, err = blockReader.IsBlockedBetween(ctx, "stream_viewer", "stream_target")
	if err != nil || blocked {
		t.Fatalf("IsBlockedBetween after unblock=%v err=%v want false", blocked, err)
	}
	blockedPersonaIDs, err = blockReader.ListBlockedPersonaIDs(ctx, "stream_viewer")
	if err != nil || len(blockedPersonaIDs) != 0 {
		t.Fatalf(
			"ListBlockedPersonaIDs after unblock=%v err=%v want empty",
			blockedPersonaIDs,
			err,
		)
	}
	var direction struct {
		Following bool `bson:"following"`
	}
	if err := relationships.FindOne(ctx, bson.M{"sourcePersonaId": "stream_viewer", "targetPersonaId": "stream_target"}).Decode(&direction); err != nil {
		t.Fatalf("read direction after unblock: %v", err)
	}
	if direction.Following {
		t.Fatalf("unblock must not restore follow state")
	}
}
