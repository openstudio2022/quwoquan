package reaction_test

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"quwoquan_service/runtime/commandmeta"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
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

func TestContentReactionOutboxRelayRetriesWithoutAdvancingFailedFact(t *testing.T) {
	t.Parallel()
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store), testBasis{})
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
	fact := store.OutboxFacts()[0]

	publisher := &reactionPublisherSpy{fail: true}
	relay := reactionapp.NewOutboxRelay(store, store, publisher, "reaction-test-consumer")
	if _, err := relay.Drain(context.Background(), 100); err == nil {
		t.Fatal("publisher failure must fail the drain")
	}
	if sequence := store.CheckpointSequence("reaction-test-consumer", fact.PartitionID); sequence != 0 {
		t.Fatalf("failed fact advanced checkpoint to %d", sequence)
	}

	publisher.fail = false
	count, err := relay.Drain(context.Background(), 100)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 || len(publisher.published) != 1 {
		t.Fatalf("expected one replayed fact, count=%d published=%v", count, publisher.published)
	}
	if sequence := store.CheckpointSequence("reaction-test-consumer", fact.PartitionID); sequence != 1 {
		t.Fatalf("successful fact checkpoint=%d, want 1", sequence)
	}
}

type partitionPublisher struct {
	poisonPartition int
	seen            map[int][]int64
}

func (p *partitionPublisher) Publish(_ context.Context, fact reactionports.OutboxFact) error {
	if p.seen == nil {
		p.seen = map[int][]int64{}
	}
	p.seen[fact.PartitionID] = append(p.seen[fact.PartitionID], fact.PartitionSequence)
	if fact.PartitionID == p.poisonPartition {
		return errors.New("poison partition")
	}
	return nil
}

func TestContentReactionRelayStopsPoisonPartitionAndContinuesAnotherPartition(t *testing.T) {
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store), testBasis{})
	factsByPartition := map[int][]reactionports.OutboxFact{}
	for index := 0; len(factsByPartition) < 2 || maxPartitionFacts(factsByPartition) < 2; index++ {
		actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, fmt.Sprintf("persona-partition-%d", index))
		if err != nil {
			t.Fatal(err)
		}
		if _, err := service.LikePost(
			commandmeta.WithIdempotencyKey(context.Background(), fmt.Sprintf("partition-key-%d", index)),
			reactionapp.LikePostCommand{PostID: fmt.Sprintf("partition-post-%d", index), Actor: actor},
		); err != nil {
			t.Fatal(err)
		}
		facts := store.OutboxFacts()
		fact := facts[len(facts)-1]
		factsByPartition[fact.PartitionID] = append(factsByPartition[fact.PartitionID], fact)
		if index > 5000 {
			t.Fatal("failed to create partition fixture")
		}
	}
	poisonPartition := -1
	healthyPartition := -1
	for partitionID, facts := range factsByPartition {
		if len(facts) >= 2 && poisonPartition < 0 {
			poisonPartition = partitionID
			continue
		}
		if partitionID != poisonPartition && healthyPartition < 0 {
			healthyPartition = partitionID
		}
	}
	if healthyPartition < 0 {
		for partitionID := range factsByPartition {
			if partitionID != poisonPartition {
				healthyPartition = partitionID
				break
			}
		}
	}
	publisher := &partitionPublisher{poisonPartition: poisonPartition}
	drained, err := reactionapp.NewOutboxRelay(store, store, publisher, "partition-isolation").Drain(context.Background(), 100)
	if err == nil {
		t.Fatal("poison partition must surface an error")
	}
	if drained == 0 || len(publisher.seen[healthyPartition]) == 0 {
		t.Fatalf("healthy partition did not continue: drained=%d seen=%v", drained, publisher.seen)
	}
	if len(publisher.seen[poisonPartition]) != 1 {
		t.Fatalf("poison successor was published: %v", publisher.seen[poisonPartition])
	}
	poisonSequence := store.CheckpointSequence("partition-isolation", poisonPartition)
	healthySequence := store.CheckpointSequence("partition-isolation", healthyPartition)
	if poisonSequence != 0 || healthySequence == 0 {
		t.Fatalf("poison=%d healthy=%d", poisonSequence, healthySequence)
	}
}

func maxPartitionFacts(facts map[int][]reactionports.OutboxFact) int {
	max := 0
	for _, partitionFacts := range facts {
		if len(partitionFacts) > max {
			max = len(partitionFacts)
		}
	}
	return max
}
