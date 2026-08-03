package reaction_test

import (
	"context"
	"errors"
	"testing"
	"time"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

type reactionPublisherSpy struct {
	fail      bool
	published []string
}

func (s *reactionPublisherSpy) Publish(
	_ context.Context,
	fact reactionports.OutboxFact,
) error {
	if s.fail {
		return errors.New("publisher unavailable")
	}
	s.published = append(s.published, fact.EventID)
	return nil
}

type likeCountProjectionSpy struct {
	postID string
	count  int64
	writes int
}

type personaLikeCountProjectionSpy struct {
	personaID string
	count     int64
	writes    int
}

func (s *personaLikeCountProjectionSpy) SetPersonaLikeCount(
	_ context.Context,
	personaID string,
	count int64,
	_ time.Time,
) error {
	s.personaID = personaID
	s.count = count
	s.writes++
	return nil
}

func (s *likeCountProjectionSpy) SetLikeCount(
	_ context.Context,
	postID string,
	count int64,
) (bool, error) {
	s.postID = postID
	s.count = count
	s.writes++
	return true, nil
}

func TestContentReactionOutboxRelayRetriesWithoutAdvancingFailedFact(t *testing.T) {
	t.Parallel()
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-relay")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.LikePost(
		commandmeta.WithIdempotencyKey(context.Background(), "reaction-relay-like"),
		reactionapp.LikePostCommand{PostID: "post-relay", Actor: actor},
	); err != nil {
		t.Fatal(err)
	}

	publisher := &reactionPublisherSpy{fail: true}
	relay := reactionapp.NewOutboxRelay(store, store, publisher, "reaction-test-consumer")
	if _, err := relay.Drain(context.Background(), 100); err == nil {
		t.Fatal("publisher failure must fail the drain")
	}
	checkpoint, err := store.LoadCheckpoint(context.Background(), "reaction-test-consumer")
	if err != nil {
		t.Fatal(err)
	}
	if checkpoint != "" {
		t.Fatalf("failed fact advanced checkpoint to %q", checkpoint)
	}

	publisher.fail = false
	count, err := relay.Drain(context.Background(), 100)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 || len(publisher.published) != 1 {
		t.Fatalf("expected one replayed fact, count=%d published=%v", count, publisher.published)
	}
	checkpoint, _ = store.LoadCheckpoint(context.Background(), "reaction-test-consumer")
	if checkpoint != "1" {
		t.Fatalf("successful fact checkpoint=%q, want 1", checkpoint)
	}
}

func TestActiveReactionCountProjectorRebuildsFromRelationsOnReplay(t *testing.T) {
	t.Parallel()
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	for index, dimension := range []reactiondomain.ActorDimension{
		reactiondomain.ActorDimensionPersona,
		reactiondomain.ActorDimensionDevice,
	} {
		actor, err := reactiondomain.NewActor(dimension, "actor-"+string(rune('a'+index)))
		if err != nil {
			t.Fatal(err)
		}
		if _, err := service.LikePost(
			commandmeta.WithIdempotencyKey(context.Background(), "reaction-project-"+string(rune('a'+index))),
			reactionapp.LikePostCommand{PostID: "post-project", Actor: actor},
		); err != nil {
			t.Fatal(err)
		}
	}
	facts := store.OutboxFacts()
	if len(facts) != 2 {
		t.Fatalf("facts=%d, want 2", len(facts))
	}
	writes := &likeCountProjectionSpy{}
	projector := reactionapp.NewActiveReactionCountProjector(store, writes)
	if err := projector.Publish(context.Background(), facts[1]); err != nil {
		t.Fatal(err)
	}
	if err := projector.Publish(context.Background(), facts[1]); err != nil {
		t.Fatal(err)
	}
	if writes.postID != "post-project" || writes.count != 2 || writes.writes != 2 {
		t.Fatalf("projection must recompute idempotently, got %+v", writes)
	}
}

func TestPersonaLikeCountProjectorIsExactReplaySafeAndExcludesDevice(t *testing.T) {
	t.Parallel()
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	persona, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-project")
	if err != nil {
		t.Fatal(err)
	}
	device, err := reactiondomain.NewActor(reactiondomain.ActorDimensionDevice, "device-project")
	if err != nil {
		t.Fatal(err)
	}
	for index, postID := range []string{"post-project-a", "post-project-b"} {
		if _, err := service.LikePost(
			commandmeta.WithIdempotencyKey(context.Background(), "persona-project-"+postID),
			reactionapp.LikePostCommand{PostID: postID, Actor: persona},
		); err != nil {
			t.Fatal(err)
		}
		if index == 0 {
			if _, err := service.LikePost(
				commandmeta.WithIdempotencyKey(context.Background(), "device-project-like"),
				reactionapp.LikePostCommand{PostID: postID, Actor: device},
			); err != nil {
				t.Fatal(err)
			}
		}
	}
	facts := store.OutboxFacts()
	if len(facts) != 3 {
		t.Fatalf("facts=%d, want 3", len(facts))
	}
	writes := &personaLikeCountProjectionSpy{}
	projector := reactionapp.NewPersonaLikeCountProjector(store, writes)
	if err := projector.Publish(context.Background(), facts[1]); err != nil {
		t.Fatal(err)
	}
	if writes.writes != 0 {
		t.Fatalf("device fact entered persona projection: %+v", writes)
	}
	if err := projector.Publish(context.Background(), facts[2]); err != nil {
		t.Fatal(err)
	}
	if err := projector.Publish(context.Background(), facts[2]); err != nil {
		t.Fatal(err)
	}
	if writes.personaID != persona.ID || writes.count != 2 || writes.writes != 2 {
		t.Fatalf("persona projection must recompute idempotently, got %+v", writes)
	}
}
