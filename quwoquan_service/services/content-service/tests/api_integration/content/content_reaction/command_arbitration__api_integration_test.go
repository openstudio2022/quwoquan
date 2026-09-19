// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#gwt-005
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#gwt-007
package content_reaction_test

import (
	"context"
	"strings"
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

func newReactionArbitrationFixture(t *testing.T) (
	*reactionpersistence.MongoContentReactionStore,
	*reactionapp.Service,
	*testinfra.RealMongo,
) {
	t.Helper()
	runtime, err := testinfra.StartRealMongo(context.Background(), "content_reaction_arbitration")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := reactionpersistence.NewMongoContentReactionStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure ContentReaction indexes: %v", err)
	}
	signer, err := reactionpersistence.NewReactionMutationBasisSigner("content-service.test", "test", []reactionpersistence.ReactionMutationBasisKey{{ID: "test", Material: []byte(strings.Repeat("k", 32))}})
	if err != nil {
		t.Fatal(err)
	}
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, liveTargetReader{}), signer)
	return store, service, runtime
}

func likeContext(ctx context.Context, key string) context.Context {
	return commandmeta.WithIdempotencyKey(ctx, key)
}
func postEvidence(t *testing.T, ctx context.Context, service *reactionapp.Service, post string, actor reactiondomain.Actor) reactionapp.MutationEvidence {
	t.Helper()
	identity, err := reactiondomain.NewPostIdentity(post, actor)
	if err != nil {
		t.Fatal(err)
	}
	basis, err := service.GetContentReactionMutationBasis(ctx, reactionapp.GetContentReactionMutationBasisQuery{Identity: identity})
	if err != nil {
		t.Fatal(err)
	}
	return reactionapp.MutationEvidence{MutationBasis: basis.MutationBasis, ExpectedVersion: basis.ExpectedVersion}
}

func TestReactionNoopAdvancesVersionFenceWithoutBusinessEvent(t *testing.T) {
	store, service, runtime := newReactionArbitrationFixture(t)
	ctx := context.Background()
	actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-noop")
	if err != nil {
		t.Fatal(err)
	}

	first, err := service.LikePost(likeContext(ctx, "noop-like-1"), reactionapp.LikePostCommand{PostID: "post-noop", Actor: actor, Evidence: postEvidence(t, ctx, service, "post-noop", actor)})
	if err != nil {
		t.Fatalf("first like: %v", err)
	}
	if !first.Changed {
		t.Fatal("first like must report a business change")
	}
	eventsAfterFirst := countReactionOutbox(t, ctx, runtime, first.ReactionID)

	// 同 actor 同目标再次点赞是新接纳的无变化决定：推进版本栅栏，但不产生业务事件。
	repeat, err := service.LikePost(likeContext(ctx, "noop-like-2"), reactionapp.LikePostCommand{PostID: "post-noop", Actor: actor, Evidence: postEvidence(t, ctx, service, "post-noop", actor)})
	if err != nil {
		t.Fatalf("repeat like: %v", err)
	}
	if repeat.Changed {
		t.Fatal("repeat like must not report a business change")
	}
	if repeat.Version <= first.Version {
		t.Fatalf("no-op must advance the version fence: first=%d repeat=%d", first.Version, repeat.Version)
	}
	if got := countReactionOutbox(t, ctx, runtime, first.ReactionID); got != eventsAfterFirst {
		t.Fatalf("no-op emitted business events: before=%d after=%d", eventsAfterFirst, got)
	}

	// 版本栅栏真实落库：旧 expectedVersion 不能再提交。
	stored := loadReactionVersion(t, ctx, runtime, first.ReactionID)
	if stored != repeat.Version {
		t.Fatalf("stored version=%d, want %d", stored, repeat.Version)
	}

	_ = store
}

func TestReactionReceiptRetainsAtLeastNinetySixHours(t *testing.T) {
	_, service, runtime := newReactionArbitrationFixture(t)
	ctx := context.Background()
	actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-retention")
	if err != nil {
		t.Fatal(err)
	}
	result, err := service.LikePost(likeContext(ctx, "retention-like"), reactionapp.LikePostCommand{PostID: "post-retention", Actor: actor, Evidence: postEvidence(t, ctx, service, "post-retention", actor)})
	if err != nil {
		t.Fatal(err)
	}
	var receipt struct {
		CreatedAt time.Time `bson:"createdAt"`
		ExpiresAt time.Time `bson:"expiresAt"`
	}
	if err := runtime.Database.
		Collection("content_reaction_command_receipts").
		FindOne(ctx, bson.D{{Key: "commandName", Value: "LikePost"}}).
		Decode(&receipt); err != nil {
		t.Fatalf("read reaction receipt: %v", err)
	}
	if retention := receipt.ExpiresAt.Sub(receipt.CreatedAt); retention < 96*time.Hour {
		t.Fatalf("receipt retention=%s, want at least 96h", retention)
	}
	if result.ReactionID == "" {
		t.Fatal("committed like must return its reaction identity")
	}
}

func TestReactionLifecycleFenceStopsLateLikeAfterDeletionSweep(t *testing.T) {
	store, service, runtime := newReactionArbitrationFixture(t)
	ctx := context.Background()
	const postID = "post-deleted-race"
	target := reactiondomain.Target{Kind: reactiondomain.TargetKindPost, ID: postID}

	earlyActor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-early")
	if err != nil {
		t.Fatal(err)
	}
	lateActor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-late")
	if err != nil {
		t.Fatal(err)
	}

	// 屏障一：目标资格检查通过并已提交的互动。
	if _, err := service.LikePost(likeContext(ctx, "race-early-like"), reactionapp.LikePostCommand{PostID: postID, Actor: earlyActor, Evidence: postEvidence(t, ctx, service, postID, earlyActor)}); err != nil {
		t.Fatalf("early like: %v", err)
	}

	// 删除消费者先封闭该 target 的全部固定桶，再清理成员。
	if err := store.CloseTargetLifecycle(ctx, target, "post-deleted:test-event"); err != nil {
		t.Fatalf("close lifecycle fences: %v", err)
	}

	// 屏障二：封闭之后到达的 Like 必须在自己的事务里失败，而不是复活贡献。
	if _, err := service.LikePost(likeContext(ctx, "race-late-like"), reactionapp.LikePostCommand{PostID: postID, Actor: lateActor, Evidence: postEvidence(t, ctx, service, postID, lateActor)}); err == nil {
		t.Fatal("late like after the fence closed must fail")
	}

	// 屏障三：清理扫空之后再次到达的 Like 同样不能新增活跃贡献。
	if _, err := service.LikePost(likeContext(ctx, "race-post-sweep-like"), reactionapp.LikePostCommand{PostID: postID, Actor: lateActor, Evidence: postEvidence(t, ctx, service, postID, lateActor)}); err == nil {
		t.Fatal("late like after the sweep must still fail")
	}

	active := countActiveReactionsForTarget(t, ctx, runtime, postID)
	if active != 1 {
		t.Fatalf("closed target holds %d active reactions from late writers, want only the pre-close one", active)
	}

	// 已封闭目标仍允许撤销与内部清理收敛为 none。
	if _, err := service.UnlikePost(likeContext(ctx, "race-early-unlike"), reactionapp.UnlikePostCommand{PostID: postID, Actor: earlyActor, Evidence: postEvidence(t, ctx, service, postID, earlyActor)}); err != nil {
		t.Fatalf("revoking an existing reaction on a closed target must converge: %v", err)
	}
	if got := countActiveReactionsForTarget(t, ctx, runtime, postID); got != 0 {
		t.Fatalf("active reactions=%d after revoke, want 0", got)
	}

	// 全部固定桶都已封闭，包括封闭时尚未创建的桶。
	closed, total := countFenceBuckets(t, ctx, runtime, postID)
	if total != 16 || closed != total {
		t.Fatalf("fence buckets closed=%d total=%d, want all 16 closed", closed, total)
	}
}

func countReactionOutbox(
	t *testing.T,
	ctx context.Context,
	runtime *testinfra.RealMongo,
	aggregateID string,
) int64 {
	t.Helper()
	count, err := runtime.Database.
		Collection("content_reaction_outbox").
		CountDocuments(ctx, bson.D{{Key: "aggregateId", Value: aggregateID}})
	if err != nil {
		t.Fatal(err)
	}
	return count
}

func loadReactionVersion(
	t *testing.T,
	ctx context.Context,
	runtime *testinfra.RealMongo,
	aggregateID string,
) int64 {
	t.Helper()
	var document struct {
		Version int64 `bson:"version"`
	}
	if err := runtime.Database.
		Collection("content_reaction_aggregates").
		FindOne(ctx, bson.D{{Key: "_id", Value: aggregateID}}).
		Decode(&document); err != nil {
		t.Fatal(err)
	}
	return document.Version
}

func countActiveReactionsForTarget(
	t *testing.T,
	ctx context.Context,
	runtime *testinfra.RealMongo,
	postID string,
) int64 {
	t.Helper()
	count, err := runtime.Database.
		Collection("content_reaction_aggregates").
		CountDocuments(ctx, bson.D{
			{Key: "targetKind", Value: "post"},
			{Key: "targetId", Value: postID},
			{Key: "reaction", Value: "like"},
		})
	if err != nil {
		t.Fatal(err)
	}
	return count
}

func countFenceBuckets(
	t *testing.T,
	ctx context.Context,
	runtime *testinfra.RealMongo,
	postID string,
) (closed int64, total int64) {
	t.Helper()
	collection := runtime.Database.Collection("content_reaction_target_fence_buckets")
	total, err := collection.CountDocuments(ctx, bson.D{
		{Key: "targetKind", Value: "post"},
		{Key: "targetId", Value: postID},
	})
	if err != nil {
		t.Fatal(err)
	}
	closed, err = collection.CountDocuments(ctx, bson.D{
		{Key: "targetKind", Value: "post"},
		{Key: "targetId", Value: postID},
		{Key: "closed", Value: true},
	})
	if err != nil {
		t.Fatal(err)
	}
	return closed, total
}

func TestReactionCleanupJobLeaseFencesOldWorkersAndResumesCheckpoint(t *testing.T) {
	store, _, _ := newReactionArbitrationFixture(t)
	ctx := context.Background()
	now := time.Now().UTC()
	target := reactiondomain.Target{Kind: reactiondomain.TargetKindPost, ID: "cleanup-job-post"}
	created, err := store.Ensure(ctx, reactionapp.LifecycleCleanupJob{ID: "cleanup-job-1", Target: target, SourceVersion: 7, Deadline: now.Add(time.Minute)})
	if err != nil {
		t.Fatal(err)
	}
	if created.SourceVersion != 7 {
		t.Fatalf("created=%+v", created)
	}
	first, ok, err := store.Claim(ctx, created.ID, now, time.Second)
	if err != nil || !ok {
		t.Fatalf("first claim=%+v ok=%v err=%v", first, ok, err)
	}
	// Let the lease expire and let a new worker claim a higher epoch.
	second, ok, err := store.Claim(ctx, created.ID, now.Add(2*time.Second), time.Second)
	if err != nil || !ok || second.LeaseEpoch <= first.LeaseEpoch {
		t.Fatalf("second=%+v first=%+v ok=%v err=%v", second, first, ok, err)
	}
	if err := store.Advance(ctx, created.ID, first.LeaseEpoch, "old", 500, false); err == nil {
		t.Fatal("old worker advanced checkpoint")
	}
	if err := store.Advance(ctx, created.ID, second.LeaseEpoch, "member-500", 500, false); err != nil {
		t.Fatal(err)
	}
	resumed, ok, err := store.Claim(ctx, created.ID, now.Add(4*time.Second), time.Second)
	if err != nil || !ok || resumed.Cursor != "member-500" || resumed.Checkpoint != 500 {
		t.Fatalf("resumed=%+v ok=%v err=%v", resumed, ok, err)
	}
	if err := store.Advance(ctx, created.ID, resumed.LeaseEpoch, resumed.Cursor, resumed.Checkpoint, true); err != nil {
		t.Fatal(err)
	}
	if _, ok, err := store.Claim(ctx, created.ID, now.Add(6*time.Second), time.Second); err != nil || ok {
		t.Fatalf("completed job reclaimed ok=%v err=%v", ok, err)
	}
}

func TestReactionReceiptsAreActorScopedAndExpirationCannotResurrect(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "content_reaction_actor_receipts")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = runtime.Close(context.Background()) })
	now := time.Now().UTC()
	store := reactionpersistence.NewMongoContentReactionStore(runtime.Database).WithClock(func() time.Time { return now })
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	signer, err := reactionpersistence.NewReactionMutationBasisSigner("content-service.test", "test", []reactionpersistence.ReactionMutationBasisKey{{ID: "test", Material: []byte(strings.Repeat("k", 32))}})
	if err != nil {
		t.Fatal(err)
	}
	signer.WithClock(func() time.Time { return now })
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, liveTargetReader{}), signer)
	ctx := context.Background()
	actorA, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "actor-a")
	actorB, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "actor-b")
	for _, actor := range []reactiondomain.Actor{actorA, actorB} {
		e := postEvidence(t, ctx, service, "same-key-post", actor)
		if _, err := service.LikePost(likeContext(ctx, "same-client-key"), reactionapp.LikePostCommand{PostID: "same-key-post", Actor: actor, Evidence: e}); err != nil {
			t.Fatal(err)
		}
	}
	count, err := runtime.Database.Collection("content_reaction_command_receipts").CountDocuments(ctx, bson.M{"idempotencyDigest": bson.M{"$exists": true}})
	if err != nil || count != 2 {
		t.Fatalf("actor scoped receipts=%d err=%v", count, err)
	}
	// Finalize wins for an unexecuted command after its signed deadline.
	expireActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "actor-expire")
	identity, _ := reactiondomain.NewPostIdentity("expire-post", expireActor)
	basis, err := service.GetContentReactionMutationBasis(ctx, reactionapp.GetContentReactionMutationBasisQuery{Identity: identity})
	if err != nil {
		t.Fatal(err)
	}
	evidence := reactionapp.MutationEvidence{MutationBasis: basis.MutationBasis, ExpectedVersion: basis.ExpectedVersion}
	now = now.Add(73 * time.Hour)
	finalized, err := service.FinalizeExpiredCommand(likeContext(ctx, "expire-key"), reactionapp.FinalizeExpiredContentReactionCommand{Identity: identity, CommandName: "LikePost", Desired: reactiondomain.ValueLike, IdempotencyKey: "expire-key", Evidence: evidence})
	if err != nil || finalized.Outcome != string(reactionports.ReceiptOutcomeExpired) {
		t.Fatalf("finalized=%+v err=%v", finalized, err)
	}
	if _, err := service.LikePost(likeContext(ctx, "expire-key"), reactionapp.LikePostCommand{PostID: "expire-post", Actor: expireActor, Evidence: evidence}); err == nil {
		t.Fatal("expired command executed")
	}
	if _, err := runtime.Database.Collection("content_reaction_command_receipts").DeleteMany(ctx, bson.M{"actorId": "actor-expire"}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.LikePost(likeContext(ctx, "expire-key"), reactionapp.LikePostCommand{PostID: "expire-post", Actor: expireActor, Evidence: evidence}); err == nil {
		t.Fatal("deleted receipt resurrected expired basis")
	}
}
