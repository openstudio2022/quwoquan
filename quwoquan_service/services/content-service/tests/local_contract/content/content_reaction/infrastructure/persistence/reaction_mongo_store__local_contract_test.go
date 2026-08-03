package persistence_test

import (
	. "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	"strings"
	"testing"
	"time"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

func TestReactionMongoDocumentRoundTripPreservesRelationIdentity(t *testing.T) {
	t.Parallel()

	actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionDevice, "device-1")
	if err != nil {
		t.Fatalf("actor: %v", err)
	}
	identity, err := reactiondomain.NewPostIdentity("post-1", actor)
	if err != nil {
		t.Fatalf("identity: %v", err)
	}
	aggregate, err := reactiondomain.New(identity, reactiondomain.ValueLike, time.Now().UTC())
	if err != nil {
		t.Fatalf("aggregate: %v", err)
	}
	restored, err := ReactionFromDocument(ReactionDocumentFromSnapshot(aggregate.Snapshot()))
	if err != nil {
		t.Fatalf("round trip: %v", err)
	}
	if restored.ID() != aggregate.ID() ||
		restored.Version() != aggregate.Version() ||
		!restored.IsLiked() ||
		restored.Identity() != identity {
		t.Fatalf("reaction mapper changed aggregate: %+v", restored.Snapshot())
	}
}

func TestReactionMongoCommitRejectsWrongOutboxVersion(t *testing.T) {
	t.Parallel()

	actor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-1")
	identity, _ := reactiondomain.NewPostIdentity("post-1", actor)
	aggregate, err := reactiondomain.New(identity, reactiondomain.ValueLike, time.Now().UTC())
	if err != nil {
		t.Fatalf("aggregate: %v", err)
	}
	err = ValidateReactionCommit(reactionports.Commit{
		Aggregate:       aggregate,
		ExpectedVersion: 0,
		IdempotencyKey:  "reaction-commit",
		CommandName:     "LikePost",
		CommandDigest:   "digest",
		Changed:         true,
		Events: []reactionports.OutboxFact{{
			EventID:          "event-1",
			EventType:        reactionapp.EventTypeContentReactionSet,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version() + 1,
			Payload:          []byte(`{}`),
			OccurredAt:       time.Now().UTC(),
		}},
	})
	if err == nil || !strings.Contains(err.Error(), "version_conflict") {
		t.Fatalf("mismatched outbox version must fail, got %v", err)
	}
}
