// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001
// readiness_case: activate-circle-group-owner-api
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	grouppersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	membershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestCircleGroupCreatedActivatesOwnerBeforeOutboxCheckpoint(t *testing.T) {
	ctx := context.Background()
	database := testsupport.StartRealMongo(t, "circle_group_owner_activation")
	groupStore := grouppersistence.NewMongoAggregateStore(database)
	membershipStore := membershippersistence.NewMongoAggregateStore(database)
	if err := groupStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	if _, err := database.Collection("circle_groups").InsertOne(ctx, bson.M{
		"_id": "group-owner-api", "circleId": "circle-owner-api",
		"status": "active", "joinPolicy": "apply_only",
		"createdByPersonaId": "persona-owner", "createdAt": now, "updatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_group_outbox").InsertOne(ctx, bson.M{
		"_id":            "group-owner-api:CircleGroupCreated:1",
		"outboxSequence": int64(1), "eventType": "CircleGroupCreated",
		"aggregateId": "group-owner-api", "aggregateVersion": int64(1),
		"payloadJson": `{"groupId":"group-owner-api","circleId":"circle-owner-api","createdByPersonaId":"persona-owner"}`,
		"occurredAt":  now,
	}); err != nil {
		t.Fatal(err)
	}
	readers := membershippersistence.NewMongoReaders(database)
	commands := membershipapp.NewCommandFacade(
		membershipStore, readers, readers, readers,
	)
	relay := groupapp.NewOutboxRelay(
		groupStore,
		groupStore,
		membershipapp.NewCircleGroupOwnerProjector(commands),
		"owner-activation-api",
	)
	if count, err := relay.Drain(ctx, 10); err != nil || count != 1 {
		t.Fatalf("drain count=%d err=%v", count, err)
	}
	if count, err := database.Collection("circle_group_memberships").CountDocuments(ctx, bson.M{
		"groupId": "group-owner-api", "personaId": "persona-owner",
		"role": "owner", "state": "active",
	}); err != nil || count != 1 {
		t.Fatalf("owner state count=%d err=%v", count, err)
	}
	if checkpoint, err := groupStore.LoadCheckpoint(ctx, "owner-activation-api"); err != nil || checkpoint != "1" {
		t.Fatalf("checkpoint=%q err=%v", checkpoint, err)
	}
}
