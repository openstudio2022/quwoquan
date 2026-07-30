// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006
package reaction_test

import (
	"context"
	"reflect"
	"strings"
	"testing"
	"time"

	reactionerrors "quwoquan_service/services/content-service/generated/content/content_reaction"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

func TestContentReaction_ActorDimensionAndReceiptAreUnique(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	persona := mustReactionActor(t, reactiondomain.ActorDimensionPersona, "same-id")
	device := mustReactionActor(t, reactiondomain.ActorDimensionDevice, "same-id")

	personaContext := commandmeta.WithIdempotencyKey(context.Background(), "reaction-persona-like")
	personaCommand := reactionapp.LikePostCommand{PostID: "post-1", Actor: persona}
	personaResult, err := service.LikePost(personaContext, personaCommand)
	if err != nil {
		t.Fatalf("persona like: %v", err)
	}
	replayed, err := service.LikePost(personaContext, personaCommand)
	if err != nil {
		t.Fatalf("replay persona like: %v", err)
	}
	if !replayed.Replayed || !replayed.Changed || replayed.ReactionID != personaResult.ReactionID {
		t.Fatalf("expected receipt replay of original result, got %+v", replayed)
	}

	deviceResult, err := service.LikePost(
		commandmeta.WithIdempotencyKey(context.Background(), "reaction-device-like"),
		reactionapp.LikePostCommand{PostID: "post-1", Actor: device},
	)
	if err != nil {
		t.Fatalf("device like: %v", err)
	}
	if personaResult.ReactionID == deviceResult.ReactionID {
		t.Fatal("persona and device with the same raw id must not share an aggregate")
	}
	if store.AggregateCount() != 2 {
		t.Fatalf("expected two independent actor relations, got %d", store.AggregateCount())
	}
	facts := store.OutboxFacts()
	if len(facts) != 2 {
		t.Fatalf("duplicate command must not append another event, got %d", len(facts))
	}
	if facts[0].AggregateVersion != personaResult.Version ||
		facts[1].AggregateVersion != deviceResult.Version {
		t.Fatalf("outbox facts must carry aggregate versions: %+v", facts)
	}

	_, err = service.LikePost(
		personaContext,
		reactionapp.LikePostCommand{PostID: "post-2", Actor: persona},
	)
	if err == nil || !strings.Contains(err.Error(), "idempotency_conflict") {
		t.Fatalf("same receipt key with a new command must conflict, got %v", err)
	}
}

func TestContentReaction_ReaderReturnsSliceWithoutAggregateLeak(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	actor := mustReactionActor(t, reactiondomain.ActorDimensionDevice, "device-1")

	_, err := service.LikePost(
		commandmeta.WithIdempotencyKey(context.Background(), "reaction-read-like"),
		reactionapp.LikePostCommand{PostID: "post-reader", Actor: actor},
	)
	if err != nil {
		t.Fatalf("like before read: %v", err)
	}
	slice, err := service.GetContentReactionState(
		context.Background(),
		reactionapp.GetContentReactionStateQuery{PostID: "post-reader", Actor: actor},
	)
	if err != nil {
		t.Fatalf("read slice: %v", err)
	}
	if !slice.Found || !slice.Liked || slice.PostID != "post-reader" {
		t.Fatalf("unexpected reader slice: %+v", slice)
	}
	sliceType := reflect.TypeOf(slice)
	for _, forbidden := range []string{"Aggregate", "ActorID", "Receipt"} {
		if _, exists := sliceType.FieldByName(forbidden); exists {
			t.Fatalf("reader slice must not leak %s", forbidden)
		}
	}
}

func TestContentReaction_MissingTargetUsesObjectOwnedErrorCode(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, missingReactionTarget{}))
	actor := mustReactionActor(t, reactiondomain.ActorDimensionPersona, "persona-1")

	_, err := service.LikePost(
		commandmeta.WithIdempotencyKey(context.Background(), "reaction-target-missing"),
		reactionapp.LikePostCommand{PostID: "missing-post", Actor: actor},
	)
	if err == nil || !strings.Contains(
		err.Error(),
		reactionerrors.ErrContentReactionTargetNotFound.Error(),
	) {
		t.Fatalf("missing target must use ContentReaction-owned error, got %v", err)
	}
	if store.AggregateCount() != 0 || len(store.OutboxFacts()) != 0 {
		t.Fatalf("missing target must not mutate aggregate or outbox")
	}
}

type missingReactionTarget struct{}

func (missingReactionTarget) FindReactionTarget(
	context.Context,
	reactiondomain.Target,
) (reactionapp.ReactionTargetSlice, error) {
	return reactionapp.ReactionTargetSlice{}, nil
}

func TestContentReaction_CommentThreeStateUsesOneAggregateAndExactCounts(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	actor := mustReactionActor(t, reactiondomain.ActorDimensionPersona, "comment-actor")
	command := reactionapp.ReactToCommentCommand{
		CommentID: "comment-target",
		Actor:     actor,
		Reaction:  reactiondomain.ValueLike,
	}
	liked, err := service.ReactToComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-reaction-like"),
		command,
	)
	if err != nil || liked.Reaction != reactiondomain.ValueLike || liked.LikeCount != 1 || liked.DislikeCount != 0 {
		t.Fatalf("comment like result=%+v err=%v", liked, err)
	}
	command.Reaction = reactiondomain.ValueDislike
	disliked, err := service.ReactToComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-reaction-dislike"),
		command,
	)
	if err != nil || disliked.Version != liked.Version+1 || disliked.LikeCount != 0 || disliked.DislikeCount != 1 {
		t.Fatalf("comment dislike result=%+v err=%v", disliked, err)
	}
	command.Reaction = reactiondomain.ValueNone
	cleared, err := service.ReactToComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-reaction-none"),
		command,
	)
	if err != nil || cleared.Reaction != reactiondomain.ValueNone || cleared.LikeCount != 0 || cleared.DislikeCount != 0 {
		t.Fatalf("comment clear result=%+v err=%v", cleared, err)
	}
	if store.AggregateCount() != 1 {
		t.Fatalf("three-state membership must retain one aggregate, got %d", store.AggregateCount())
	}
}

func TestContentReaction_StaleLikeAfterUnlikeIsRejected(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	actor := mustReactionActor(t, reactiondomain.ActorDimensionPersona, "persona-1")
	initial, err := service.LikePost(
		commandmeta.WithIdempotencyKey(context.Background(), "reaction-race-initial"),
		reactionapp.LikePostCommand{PostID: "post-race", Actor: actor},
	)
	if err != nil {
		t.Fatalf("initial like: %v", err)
	}

	winner, found, err := store.Load(context.Background(), initial.ReactionID)
	if err != nil || !found {
		t.Fatalf("load winner state: found=%v err=%v", found, err)
	}
	stale, found, err := store.Load(context.Background(), initial.ReactionID)
	if err != nil || !found {
		t.Fatalf("load stale state: found=%v err=%v", found, err)
	}
	now := time.Now().UTC().Add(time.Second)
	changed, err := winner.Set(reactiondomain.ValueNone, now)
	if err != nil || !changed {
		t.Fatalf("winner unlike: changed=%v err=%v", changed, err)
	}
	if _, err := store.Commit(context.Background(), reactionports.Commit{
		Aggregate:       winner,
		ExpectedVersion: initial.Version,
		IdempotencyKey:  "reaction-race-unlike",
		CommandName:     "UnlikePost",
		CommandDigest:   "race-unlike",
		Changed:         true,
		Events: []reactionports.OutboxFact{{
			EventID:          "reaction-race-unlike-event",
			EventType:        reactionapp.EventTypeContentReactionCleared,
			AggregateID:      winner.ID(),
			AggregateVersion: winner.Version(),
			Payload:          []byte(`{"reaction":"none"}`),
			OccurredAt:       now,
		}},
	}); err != nil {
		t.Fatalf("commit winning unlike: %v", err)
	}
	if changed, err := stale.Set(reactiondomain.ValueLike, now.Add(time.Second)); err != nil || changed {
		t.Fatalf("stale like should be a local no-op before CAS: changed=%v err=%v", changed, err)
	}
	_, err = store.Commit(context.Background(), reactionports.Commit{
		Aggregate:       stale,
		ExpectedVersion: initial.Version,
		IdempotencyKey:  "reaction-race-stale-like",
		CommandName:     "LikePost",
		CommandDigest:   "race-stale-like",
	})
	if err == nil || !strings.Contains(err.Error(), "version_conflict") {
		t.Fatalf("stale like must be rejected by version CAS, got %v", err)
	}
	current, found, err := store.Load(context.Background(), initial.ReactionID)
	if err != nil || !found || current.IsLiked() {
		t.Fatalf("winner state must remain removed: found=%v liked=%v err=%v", found, current != nil && current.IsLiked(), err)
	}
	facts := store.OutboxFacts()
	if len(facts) != 2 || facts[1].AggregateVersion != 2 {
		t.Fatalf("race must produce one version-2 removal fact, got %+v", facts)
	}
}

func mustReactionActor(
	t *testing.T,
	dimension reactiondomain.ActorDimension,
	id string,
) reactiondomain.Actor {
	t.Helper()
	actor, err := reactiondomain.NewActor(dimension, id)
	if err != nil {
		t.Fatalf("new actor: %v", err)
	}
	return actor
}
