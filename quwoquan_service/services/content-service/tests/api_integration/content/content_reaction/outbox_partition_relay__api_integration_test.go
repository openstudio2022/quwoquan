// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#gwt-008
package content_reaction_test

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	reactionmessaging "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/messaging"
)

type poisonReactionPublisher struct {
	publisher *reactionmessaging.ReactionLifecycleStreamPublisher
	poison    string
}

func (publisher *poisonReactionPublisher) Publish(ctx context.Context, fact reactionports.OutboxFact) error {
	if fact.EventID == publisher.poison {
		return errors.New("poison transport event")
	}
	return publisher.publisher.Publish(ctx, fact)
}

func TestContentReactionPartitionRelayUsesRealMongoRedisAndFencesOldWorker(t *testing.T) {
	store, service, runtime := newReactionArbitrationFixture(t)
	ctx := context.Background()
	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = redisRuntime.Close(context.Background()) })
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{"general": {
			Mode: "standalone", Addr: redisRuntime.Addr, Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
		}}, DefaultScene: "general",
	})
	t.Cleanup(func() { _ = router.Close() })
	client := router.Scene("general")

	factsByPartition := map[int][]reactionports.OutboxFact{}
	for index := 0; len(factsByPartition) < 2; index++ {
		actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, fmt.Sprintf("mongo-partition-actor-%d", index))
		if err != nil {
			t.Fatal(err)
		}
		postID := fmt.Sprintf("mongo-partition-post-%d", index)
		evidence := postEvidence(t, ctx, service, postID, actor)
		if _, err := service.LikePost(likeContext(ctx, fmt.Sprintf("mongo-partition-key-%d", index)), reactionapp.LikePostCommand{PostID: postID, Actor: actor, Evidence: evidence}); err != nil {
			t.Fatal(err)
		}
		identity, err := reactiondomain.NewPostIdentity(postID, actor)
		if err != nil {
			t.Fatal(err)
		}
		var document struct {
			ID                string `bson:"_id"`
			PartitionKey      string `bson:"partitionKey"`
			PartitionID       int    `bson:"partitionId"`
			PartitionSequence int64  `bson:"partitionSequence"`
		}
		if err := runtime.Database.Collection("content_reaction_outbox").FindOne(
			ctx, map[string]any{"aggregateId": identity.AggregateID()},
		).Decode(&document); err != nil {
			t.Fatal(err)
		}
		factsByPartition[document.PartitionID] = append(factsByPartition[document.PartitionID], reactionports.OutboxFact{
			EventID: document.ID, PartitionKey: document.PartitionKey,
			PartitionID: document.PartitionID, PartitionSequence: document.PartitionSequence,
		})
		if index > 5000 {
			t.Fatal("failed to create two ContentReaction partitions")
		}
	}

	oldLeases, err := store.ClaimOutboxPartitions(ctx, "mongo-fence", "old", time.Millisecond, reactionports.ContentReactionOutboxPartitionCount)
	if err != nil {
		t.Fatal(err)
	}
	time.Sleep(10 * time.Millisecond)
	newLeases, err := store.ClaimOutboxPartitions(ctx, "mongo-fence", "new", time.Minute, reactionports.ContentReactionOutboxPartitionCount)
	if err != nil {
		t.Fatal(err)
	}
	newLease, fact := populatedReactionLease(t, ctx, store, newLeases)
	var oldLease reactionports.OutboxPartitionLease
	for _, lease := range oldLeases {
		if lease.PartitionID == newLease.PartitionID {
			oldLease = lease
			break
		}
	}
	if err := store.AdvanceOutboxCheckpoint(ctx, oldLease, fact); !errors.Is(err, reactionports.ErrOutboxLeaseLost) {
		t.Fatalf("old worker advanced checkpoint: %v", err)
	}

	publisher := &poisonReactionPublisher{
		publisher: reactionmessaging.NewReactionLifecycleStreamPublisher(client),
		poison:    fact.EventID,
	}
	drained, err := reactionapp.NewOutboxRelay(store, store, publisher, "mongo-relay-proof").Drain(ctx, 100)
	if err == nil || drained == 0 {
		t.Fatalf("drained=%d err=%v; healthy partition must continue", drained, err)
	}
	var poisonCheckpoint struct {
		Sequence int64 `bson:"sequence"`
	}
	if err := runtime.Database.Collection("content_reaction_projection_checkpoints").FindOne(
		ctx, map[string]any{"_id": fmt.Sprintf("%s:%02d", "mongo-relay-proof", fact.PartitionID)},
	).Decode(&poisonCheckpoint); err != nil {
		t.Fatal(err)
	}
	if poisonCheckpoint.Sequence != 0 {
		t.Fatalf("poison checkpoint=%d, want 0", poisonCheckpoint.Sequence)
	}
	messages, err := client.XRead(ctx, map[string]string{reactionmessaging.ReactionLifecycleStream: "0-0"}, 100, 0)
	if err != nil || len(messages) == 0 {
		t.Fatalf("read reaction Redis stream messages=%d err=%v", len(messages), err)
	}
	for _, message := range messages {
		if message.Values["eventId"] == fact.EventID {
			t.Fatal("poison ContentReaction was appended")
		}
		if message.Values["partitionKey"] != message.Values["aggregateId"] ||
			message.Values["partitionSequence"] == "" {
			t.Fatalf("reaction envelope=%v", message.Values)
		}
		if _, err := strconv.Atoi(message.Values["partitionId"]); err != nil {
			t.Fatalf("partitionId=%q", message.Values["partitionId"])
		}
	}
	legacyCount, err := runtime.Database.Collection("content_reaction_outbox_sequences").CountDocuments(ctx, map[string]any{"_id": "ContentReaction"})
	if err != nil || legacyCount != 0 {
		t.Fatalf("legacy global sequence rows=%d err=%v", legacyCount, err)
	}
	partitionCounters, err := runtime.Database.Collection("content_reaction_outbox_partition_sequences").CountDocuments(ctx, map[string]any{})
	if err != nil || partitionCounters < 2 {
		t.Fatalf("partition sequence counters=%d err=%v", partitionCounters, err)
	}
}

func populatedReactionLease(
	t *testing.T,
	ctx context.Context,
	store reactionports.OutboxReader,
	leases []reactionports.OutboxPartitionLease,
) (reactionports.OutboxPartitionLease, reactionports.OutboxFact) {
	t.Helper()
	for _, lease := range leases {
		facts, err := store.ReadOutboxPartition(ctx, lease, 1)
		if err == nil && len(facts) > 0 {
			return lease, facts[0]
		}
	}
	t.Fatal("no populated ContentReaction partition")
	return reactionports.OutboxPartitionLease{}, reactionports.OutboxFact{}
}
