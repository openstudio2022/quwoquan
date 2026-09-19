package content_reaction_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/commandmeta"
	rtredis "quwoquan_service/runtime/redis"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
)

func TestLifecycleCleanupCommentAccountAndPersonaConvergeOnReplicaSet(t *testing.T) {
	store, service, runtime := newReactionArbitrationFixture(t)
	adapter := reactionpersistence.NewMongoLifecycleCleanupAdapter(store)
	if err := adapter.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	service.WithActorLifecycleWriteFence(adapter)
	cleanup := reactionapp.NewLifecycleCleanupService(service, adapter, adapter, adapter, adapter)
	ctx := context.Background()

	commentActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "lifecycle-comment-actor")
	accountActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "lifecycle-account-actor")
	personaActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "lifecycle-persona-actor")
	commentIdentity, _ := reactiondomain.NewCommentIdentity("lifecycle-comment", commentActor)
	commentBasis, err := service.GetContentReactionMutationBasis(ctx, reactionapp.GetContentReactionMutationBasisQuery{Identity: commentIdentity})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.ReactToComment(commandmeta.WithIdempotencyKey(ctx, "comment-like"), reactionapp.ReactToCommentCommand{CommentID: "lifecycle-comment", Actor: commentActor, Reaction: reactiondomain.ValueLike, Evidence: reactionapp.MutationEvidence{MutationBasis: commentBasis.MutationBasis, ExpectedVersion: commentBasis.ExpectedVersion}}); err != nil {
		t.Fatal(err)
	}
	for _, pair := range []struct {
		post  string
		actor reactiondomain.Actor
		key   string
	}{{"account-post", accountActor, "account-like"}, {"persona-post", personaActor, "persona-like"}} {
		if _, err := service.LikePost(commandmeta.WithIdempotencyKey(ctx, pair.key), reactionapp.LikePostCommand{PostID: pair.post, Actor: pair.actor, Evidence: postEvidence(t, ctx, service, pair.post, pair.actor)}); err != nil {
			t.Fatal(err)
		}
	}

	now := time.Now().UTC()
	commentTarget, _ := reactiondomain.NewTarget(reactiondomain.TargetKindComment, "lifecycle-comment")
	if err := cleanup.CleanupTarget(ctx, commentTarget, lifecycleAuthorization("CommentDeleted", "comment-deleted-event", 2, now)); err != nil {
		t.Fatal(err)
	}
	if err := cleanup.CleanupActor(ctx, accountActor, lifecycleAuthorization("UserAccountClosed", "account-closed-event", 7, now)); err != nil {
		t.Fatal(err)
	}
	if err := cleanup.CleanupActor(ctx, personaActor, lifecycleAuthorization("PersonaRetired", "persona-retired-event", 4, now)); err != nil {
		t.Fatal(err)
	}

	if got := activeReactionCount(t, runtime, bson.M{"$or": bson.A{
		bson.M{"targetKind": "comment", "targetId": "lifecycle-comment"},
		bson.M{"actorId": bson.M{"$in": bson.A{accountActor.ID, personaActor.ID}}},
	}, "reaction": bson.M{"$ne": "none"}}); got != 0 {
		t.Fatalf("active lifecycle reactions=%d, want 0", got)
	}
	receipts, err := runtime.Database.Collection("content_reaction_command_receipts").CountDocuments(ctx, bson.M{"actorId": bson.M{"$in": bson.A{commentActor.ID, accountActor.ID, personaActor.ID}}})
	if err != nil || receipts < 6 {
		t.Fatalf("retained receipts=%d err=%v, want original and cleanup receipts", receipts, err)
	}
	jobs, err := runtime.Database.Collection("content_reaction_cleanup_jobs").CountDocuments(ctx, bson.M{"completed": true, "tombstone": bson.M{"$exists": true}, "sourceVersion": bson.M{"$gt": 0}})
	if err != nil || jobs != 3 {
		t.Fatalf("completed durable jobs=%d err=%v, want 3", jobs, err)
	}
}

func TestLifecycleCleanupTargetAndActorFencesRejectLateWriters(t *testing.T) {
	store, service, runtime := newReactionArbitrationFixture(t)
	adapter := reactionpersistence.NewMongoLifecycleCleanupAdapter(store)
	if err := adapter.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	service.WithActorLifecycleWriteFence(adapter)
	cleanup := reactionapp.NewLifecycleCleanupService(service, adapter, adapter, adapter, adapter)
	ctx := context.Background()
	now := time.Now().UTC()

	target, _ := reactiondomain.NewTarget(reactiondomain.TargetKindComment, "fenced-comment")
	if err := cleanup.CleanupTarget(ctx, target, lifecycleAuthorization("CommentDeleted", "fenced-comment-event", 3, now)); err != nil {
		t.Fatal(err)
	}
	lateCommentActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "late-comment-actor")
	lateCommentIdentity, _ := reactiondomain.NewCommentIdentity(target.ID, lateCommentActor)
	basis, err := service.GetContentReactionMutationBasis(ctx, reactionapp.GetContentReactionMutationBasisQuery{Identity: lateCommentIdentity})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.ReactToComment(commandmeta.WithIdempotencyKey(ctx, "late-comment-like"), reactionapp.ReactToCommentCommand{CommentID: target.ID, Actor: lateCommentActor, Reaction: reactiondomain.ValueLike, Evidence: reactionapp.MutationEvidence{MutationBasis: basis.MutationBasis, ExpectedVersion: basis.ExpectedVersion}}); err == nil {
		t.Fatal("late Comment reaction crossed closed target fence")
	}

	retiredActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "retired-actor")
	if err := cleanup.CleanupActor(ctx, retiredActor, lifecycleAuthorization("PersonaRetired", "retired-event", 8, now)); err != nil {
		t.Fatal(err)
	}
	if _, err := service.LikePost(commandmeta.WithIdempotencyKey(ctx, "late-retired-like"), reactionapp.LikePostCommand{PostID: "late-retired-post", Actor: retiredActor, Evidence: postEvidence(t, ctx, service, "late-retired-post", retiredActor)}); err == nil {
		t.Fatal("late reaction crossed closed actor fence")
	}
	if got := activeReactionCount(t, runtime, bson.M{"actorId": retiredActor.ID, "reaction": bson.M{"$ne": "none"}}); got != 0 {
		t.Fatalf("retired actor active reactions=%d", got)
	}
}

func TestCommentDeletedAndPersonaRetiredConsumersCleanupOnReplicaSet(t *testing.T) {
	store, service, runtime := newReactionArbitrationFixture(t)
	adapter := reactionpersistence.NewMongoLifecycleCleanupAdapter(store)
	if err := adapter.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	service.WithActorLifecycleWriteFence(adapter)
	cleanup := reactionapp.NewLifecycleCleanupService(service, adapter, adapter, adapter, adapter)
	ctx := context.Background()

	commentActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "consumer-comment-actor")
	commentIdentity, _ := reactiondomain.NewCommentIdentity("consumer-comment", commentActor)
	basis, err := service.GetContentReactionMutationBasis(ctx, reactionapp.GetContentReactionMutationBasisQuery{Identity: commentIdentity})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.ReactToComment(commandmeta.WithIdempotencyKey(ctx, "consumer-comment-like"), reactionapp.ReactToCommentCommand{CommentID: commentIdentity.Target.ID, Actor: commentActor, Reaction: reactiondomain.ValueLike, Evidence: reactionapp.MutationEvidence{MutationBasis: basis.MutationBasis, ExpectedVersion: basis.ExpectedVersion}}); err != nil {
		t.Fatal(err)
	}
	deletedAt := time.Now().UTC()
	payload, _ := json.Marshal(map[string]any{"commentId": commentIdentity.Target.ID, "version": int64(2), "postId": "consumer-post", "authorId": "comment-author", "deletedAt": deletedAt})
	commentConsumer := reactionapp.NewCommentDeletionConsumer(cleanup)
	if err := commentConsumer.Publish(ctx, commentports.OutboxEvent{EventID: "comment-consumer-event", EventType: "CommentDeleted", AggregateID: commentIdentity.Target.ID, AggregateVersion: 2, Payload: payload, OccurredAt: deletedAt}); err != nil {
		t.Fatal(err)
	}

	personaActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "consumer-retired-persona")
	if _, err := service.LikePost(commandmeta.WithIdempotencyKey(ctx, "consumer-persona-like"), reactionapp.LikePostCommand{PostID: "consumer-persona-post", Actor: personaActor, Evidence: postEvidence(t, ctx, service, "consumer-persona-post", personaActor)}); err != nil {
		t.Fatal(err)
	}
	redis := rtredis.NewMemoryClient()
	personaConsumer, err := reactionapp.NewPersonaRetiredConsumer(redis, cleanup, "consumer-test", nil)
	if err != nil {
		t.Fatal(err)
	}
	personaPayload, _ := json.Marshal(map[string]string{"userId": "consumer-user", "personaId": personaActor.ID})
	if _, err := redis.XAdd(ctx, reactionapp.PersonaLifecycleEventStream, map[string]string{"eventId": "persona-consumer-event", "eventName": "PersonaRetired", "personaId": personaActor.ID, "personaVersion": "5", "payload": string(personaPayload), "occurredAt": deletedAt.Format(time.RFC3339Nano)}); err != nil {
		t.Fatal(err)
	}
	if processed, err := personaConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("persona processed=%d err=%v", processed, err)
	}

	if got := activeReactionCount(t, runtime, bson.M{"$or": bson.A{bson.M{"targetId": commentIdentity.Target.ID}, bson.M{"actorId": personaActor.ID}}, "reaction": bson.M{"$ne": "none"}}); got != 0 {
		t.Fatalf("consumer cleanup active=%d", got)
	}
}

func TestLifecycleCleanupBatchResumeAndStaleEpochOnReplicaSet(t *testing.T) {
	store, service, runtime := newReactionArbitrationFixture(t)
	adapter := reactionpersistence.NewMongoLifecycleCleanupAdapter(store)
	if err := adapter.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	service.WithActorLifecycleWriteFence(adapter)
	cleanup := reactionapp.NewLifecycleCleanupService(service, adapter, adapter, adapter, adapter).WithExecutionLimitsForTest(5, 2*time.Second)
	ctx := context.Background()
	const postID = "batch-resume-post"
	for index := 0; index < 6; index++ {
		actor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, fmt.Sprintf("batch-actor-%03d", index))
		key := fmt.Sprintf("batch-like-%03d", index)
		if _, err := service.LikePost(commandmeta.WithIdempotencyKey(ctx, key), reactionapp.LikePostCommand{PostID: postID, Actor: actor, Evidence: postEvidence(t, ctx, service, postID, actor)}); err != nil {
			t.Fatal(err)
		}
	}
	target, _ := reactiondomain.NewTarget(reactiondomain.TargetKindPost, postID)
	authorization := lifecycleAuthorization("PostDeleted", "batch-delete-event", 9, time.Now().UTC())
	for attempt := 0; attempt < 10; attempt++ {
		err := cleanup.CleanupTarget(ctx, target, authorization)
		if err == nil {
			break
		}
		if !errors.Is(err, reactionapp.ErrLifecycleCleanupDeadline) {
			t.Fatal(err)
		}
		if attempt == 9 {
			t.Fatal(err)
		}
	}
	if got := activeReactionCount(t, runtime, bson.M{"targetId": postID, "reaction": bson.M{"$ne": "none"}}); got != 0 {
		t.Fatalf("batch cleanup active=%d", got)
	}
	var job bson.M
	if err := runtime.Database.Collection("content_reaction_cleanup_jobs").FindOne(ctx, bson.M{"sourceEventId": authorization.SourceEventID}).Decode(&job); err != nil {
		t.Fatal(err)
	}
	if job["checkpoint"] != int64(6) || job["completed"] != true {
		t.Fatalf("cleanup job=%v", job)
	}

	seed := reactionapp.LifecycleCleanupJob{ID: "stale-epoch-job", Scope: reactionapp.LifecycleCleanupScopeTarget, Target: target, Source: "PostDeleted", SourceEventID: "stale-epoch-event", SourceVersion: 10, Tombstone: "post:stale:v10", Deadline: time.Now().Add(time.Minute)}
	created, err := adapter.Ensure(ctx, seed)
	if err != nil {
		t.Fatal(err)
	}
	first, ok, err := adapter.Claim(ctx, created.ID, time.Now(), time.Millisecond)
	if err != nil || !ok {
		t.Fatalf("first claim ok=%v err=%v", ok, err)
	}
	second, ok, err := adapter.Claim(ctx, created.ID, time.Now().Add(time.Second), time.Second)
	if err != nil || !ok {
		t.Fatalf("second claim ok=%v err=%v", ok, err)
	}
	if err := adapter.Advance(ctx, created.ID, first.LeaseEpoch, "stale", 1, false); err == nil {
		t.Fatal("stale worker epoch advanced cleanup job")
	}
	if err := adapter.Advance(ctx, created.ID, second.LeaseEpoch, "current", 1, false); err != nil {
		t.Fatal(err)
	}
}

func lifecycleAuthorization(source, eventID string, version int64, now time.Time) reactionapp.LifecycleCleanupAuthorization {
	return reactionapp.LifecycleCleanupAuthorization{Source: source, SourceEventID: eventID, SourceVersion: version, Tombstone: fmt.Sprintf("%s:%s:v%d", source, eventID, version), OccurredAt: now}
}

func activeReactionCount(t *testing.T, runtime *testinfra.RealMongo, filter bson.M) int64 {
	t.Helper()
	count, err := runtime.Database.Collection("content_reaction_aggregates").CountDocuments(context.Background(), filter)
	if err != nil {
		t.Fatal(err)
	}
	return count
}
