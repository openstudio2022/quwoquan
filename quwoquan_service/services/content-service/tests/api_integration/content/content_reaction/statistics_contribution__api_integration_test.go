// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#gwt-008
package content_reaction_test

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/commandmeta"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
)

func TestReactionStatisticsLedgerReplayUnlikeRollupAndRepairRealMongo(t *testing.T) {
	ctx := context.Background()
	runtime, err := testinfra.StartRealMongo(ctx, fmt.Sprintf("reaction_statistics_%d", time.Now().UnixNano()))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = runtime.Close(context.Background()) })
	aggregateStore := reactionpersistence.NewMongoContentReactionStore(runtime.Database)
	if err := aggregateStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	statisticsStore := reactionpersistence.NewMongoReactionStatisticsStore(runtime.Database)
	if err := statisticsStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC().Truncate(time.Millisecond)
	like := reactionStatisticsFact(t, "event-1", 1, 1, "like", now)
	if err := statisticsStore.Publish(ctx, like); err != nil {
		t.Fatal(err)
	}
	if err := statisticsStore.Publish(ctx, like); err != nil {
		t.Fatalf("replay must be idempotent: %v", err)
	}
	assertReactionStatisticsBucket(t, ctx, runtime, "target", "post", "post-1", "like", 1)
	assertReactionStatisticsBucket(t, ctx, runtime, "actor", "persona", "persona-1", "like", 1)

	unlike := reactionStatisticsFact(t, "event-2", 2, 2, "none", now.Add(time.Second))
	if err := statisticsStore.Publish(ctx, unlike); err != nil {
		t.Fatal(err)
	}
	assertReactionStatisticsBucket(t, ctx, runtime, "target", "post", "post-1", "like", 0)

	if _, _, err := statisticsStore.Rollup(ctx, 5*time.Second); err != nil {
		t.Fatal(err)
	}
	target, _ := reactiondomain.NewTarget(reactiondomain.TargetKindPost, "post-1")
	slice, err := statisticsStore.ReadStatistics(ctx, target)
	if err != nil || slice.State != reactionapp.StatisticsAvailable || slice.Snapshot == nil || slice.Snapshot.LikeCount != 0 {
		t.Fatalf("unexpected target stats slice=%+v err=%v", slice, err)
	}

	// Build one authoritative aggregate/outbox pair through the real command
	// transaction, then corrupt only the derived ledger and repair it.
	signer, err := reactionpersistence.NewReactionMutationBasisSigner("content-service.test", "test", []reactionpersistence.ReactionMutationBasisKey{{ID: "test", Material: []byte("01234567890123456789012345678901")}})
	if err != nil {
		t.Fatal(err)
	}
	service := reactionapp.NewService(reactionapp.BindDataPorts(aggregateStore, liveTargetReader{}, statisticsStore), signer)
	actor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "repair-persona")
	identity, _ := reactiondomain.NewPostIdentity("repair-post", actor)
	basis, err := service.GetContentReactionMutationBasis(ctx, reactionapp.GetContentReactionMutationBasisQuery{Identity: identity})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.LikePost(commandmeta.WithIdempotencyKey(ctx, "repair-like"), reactionapp.LikePostCommand{PostID: "repair-post", Actor: actor, Evidence: reactionapp.MutationEvidence{MutationBasis: basis.MutationBasis, ExpectedVersion: basis.ExpectedVersion}}); err != nil {
		t.Fatal(err)
	}
	presentationBefore, err := service.GetContentReactionPresentation(ctx, identity)
	if err != nil || presentationBefore.ViewerAttachment.Reaction == nil || *presentationBefore.ViewerAttachment.Reaction != reactiondomain.ValueLike {
		t.Fatalf("presentation before=%+v err=%v", presentationBefore, err)
	}
	// Statistics remain explicitly unavailable until the statistics fact and immutable rollup generation arrive.
	if presentationBefore.Statistics.State != reactionapp.StatisticsUnavailable {
		t.Fatalf("premature statistics=%+v", presentationBefore.Statistics)
	}
	repairPayload, err := json.Marshal(map[string]any{"reactionId": identity.AggregateID(), "version": int64(1), "targetKind": "post", "targetId": "repair-post", "actorDimension": "persona", "actorId": "repair-persona", "reaction": "like", "occurredAt": now, "idempotencyKey": "repair-like"})
	if err != nil {
		t.Fatal(err)
	}
	repairFact := reactionports.OutboxFact{EventID: "repair-stats-event", EventType: reactionapp.EventTypeContentReactionSet, AggregateID: identity.AggregateID(), AggregateVersion: 1, Payload: repairPayload, OccurredAt: now, PartitionKey: identity.AggregateID(), PartitionID: reactionports.OutboxPartitionForKey(identity.AggregateID()), PartitionSequence: 1}
	if err := statisticsStore.Publish(ctx, repairFact); err != nil {
		t.Fatal(err)
	}
	if _, _, err := statisticsStore.Rollup(ctx, 5*time.Second); err != nil {
		t.Fatal(err)
	}
	presentationAfter, err := service.GetContentReactionPresentation(ctx, identity)
	if err != nil || presentationAfter.Statistics.State != reactionapp.StatisticsAvailable || presentationAfter.Statistics.Snapshot == nil || presentationAfter.Statistics.Snapshot.LikeCount != 1 {
		t.Fatalf("presentation after=%+v err=%v", presentationAfter, err)
	}
	if _, err := runtime.Database.Collection("content_reaction_statistics_buckets").UpdateMany(ctx, bson.M{"generation": "live"}, bson.M{"$set": bson.M{"value": 9}}); err != nil {
		t.Fatal(err)
	}
	if _, err := statisticsStore.Repair(ctx); err != nil {
		t.Fatal(err)
	}
	assertReactionStatisticsBucket(t, ctx, runtime, "target", "post", "repair-post", "like", 1)
}

func TestReactionStatisticsRejectsSameVersionDifferentDigestRealMongo(t *testing.T) {
	ctx := context.Background()
	runtime, err := testinfra.StartRealMongo(ctx, fmt.Sprintf("reaction_statistics_digest_%d", time.Now().UnixNano()))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = runtime.Close(context.Background()) })
	store := reactionpersistence.NewMongoReactionStatisticsStore(runtime.Database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	if err := store.Publish(ctx, reactionStatisticsFact(t, "event-a", 1, 1, "like", now)); err != nil {
		t.Fatal(err)
	}
	if err := store.Publish(ctx, reactionStatisticsFact(t, "event-b", 1, 2, "none", now)); err == nil {
		t.Fatal("same member version with different after-state must fail")
	}
}

func reactionStatisticsFact(t *testing.T, eventID string, version, checkpoint int64, reaction string, occurredAt time.Time) reactionports.OutboxFact {
	t.Helper()
	actor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-1")
	identity, _ := reactiondomain.NewPostIdentity("post-1", actor)
	payload, err := json.Marshal(map[string]any{
		"reactionId": identity.AggregateID(), "version": version,
		"targetKind": "post", "targetId": "post-1",
		"actorDimension": "persona", "actorId": "persona-1",
		"reaction": reaction, "occurredAt": occurredAt,
		"idempotencyKey": eventID,
	})
	if err != nil {
		t.Fatal(err)
	}
	eventType := reactionapp.EventTypeContentReactionSet
	if reaction == "none" {
		eventType = reactionapp.EventTypeContentReactionCleared
	}
	return reactionports.OutboxFact{
		EventID: eventID, EventType: eventType, AggregateID: identity.AggregateID(),
		AggregateVersion: version, Payload: payload, OccurredAt: occurredAt,
		PartitionKey: identity.AggregateID(), PartitionID: reactionports.OutboxPartitionForKey(identity.AggregateID()), PartitionSequence: checkpoint,
	}
}

func assertReactionStatisticsBucket(t *testing.T, ctx context.Context, runtime *testinfra.RealMongo, dimension, ownerKind, ownerID, contributionKind string, want int64) {
	t.Helper()
	pipeline := []bson.D{
		{{Key: "$match", Value: bson.M{"generation": "live", "dimension": dimension, "ownerKind": ownerKind, "ownerId": ownerID, "contributionKind": contributionKind}}},
		{{Key: "$group", Value: bson.M{"_id": nil, "value": bson.M{"$sum": "$value"}}}},
	}
	cursor, err := runtime.Database.Collection("content_reaction_statistics_buckets").Aggregate(ctx, pipeline)
	if err != nil {
		t.Fatal(err)
	}
	defer cursor.Close(ctx)
	var row struct {
		Value int64 `bson:"value"`
	}
	got := int64(0)
	if cursor.Next(ctx) {
		if err := cursor.Decode(&row); err != nil {
			t.Fatal(err)
		}
		got = row.Value
	}
	if got != want {
		t.Fatalf("reaction statistics %s/%s/%s/%s=%d want=%d", dimension, ownerKind, ownerID, contributionKind, got, want)
	}
}
