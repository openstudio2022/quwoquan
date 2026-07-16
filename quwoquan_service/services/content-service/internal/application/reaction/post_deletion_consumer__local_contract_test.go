package reaction_test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestPostDeletionConsumerTransitionsEachReactionAndIsReplaySafe(t *testing.T) {
	t.Parallel()
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	for index, actor := range []reactiondomain.Actor{
		mustReactionActor(t, reactiondomain.ActorDimensionPersona, "persona-delete"),
		mustReactionActor(t, reactiondomain.ActorDimensionDevice, "device-delete"),
	} {
		if _, err := service.LikePost(
			commandmeta.WithIdempotencyKey(context.Background(), "delete-like-"+string(rune('a'+index))),
			reactionapp.LikePostCommand{PostID: "post-delete", Actor: actor},
		); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := service.LikePost(
		commandmeta.WithIdempotencyKey(context.Background(), "keep-like"),
		reactionapp.LikePostCommand{
			PostID: "post-keep",
			Actor:  mustReactionActor(t, reactiondomain.ActorDimensionPersona, "persona-delete"),
		},
	); err != nil {
		t.Fatal(err)
	}

	consumer := reactionapp.NewPostDeletionConsumer(service, store)
	event := postDeletedOutboxEvent(t, "post-delete", "post-delete-event")
	if err := consumer.Publish(context.Background(), event); err != nil {
		t.Fatal(err)
	}
	if err := consumer.Publish(context.Background(), event); err != nil {
		t.Fatalf("replay PostDeleted: %v", err)
	}
	deletedCount, err := store.CountActiveReactions(context.Background(), "post-delete")
	if err != nil || deletedCount != 0 {
		t.Fatalf("deleted Post active reactions=%d err=%v", deletedCount, err)
	}
	keptCount, err := store.CountActiveReactions(context.Background(), "post-keep")
	if err != nil || keptCount != 1 {
		t.Fatalf("foreign Post active reactions=%d err=%v", keptCount, err)
	}
	facts := store.OutboxFacts()
	if len(facts) != 5 {
		t.Fatalf("facts=%d, want 3 activations + 2 removals", len(facts))
	}
	for _, fact := range facts[3:] {
		if fact.EventType != reactionapp.EventTypeContentReactionCleared {
			t.Fatalf("deletion emitted %q, want ContentReactionCleared", fact.EventType)
		}
	}
}

func TestPostDeletionConsumerRejectsMixedPayloadWithoutMutation(t *testing.T) {
	t.Parallel()
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	actor := mustReactionActor(t, reactiondomain.ActorDimensionPersona, "persona-invalid-delete")
	if _, err := service.LikePost(
		commandmeta.WithIdempotencyKey(context.Background(), "invalid-delete-like"),
		reactionapp.LikePostCommand{PostID: "post-invalid-delete", Actor: actor},
	); err != nil {
		t.Fatal(err)
	}
	event := postDeletedOutboxEvent(t, "post-invalid-delete", "post-invalid-delete-event")
	var payload map[string]any
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		t.Fatal(err)
	}
	payload["unsupportedReactionCascade"] = true
	event.Payload, _ = json.Marshal(payload)
	consumer := reactionapp.NewPostDeletionConsumer(service, store)
	if err := consumer.Publish(context.Background(), event); err == nil {
		t.Fatal("mixed unsupported PostDeleted payload must be rejected")
	}
	count, err := store.CountActiveReactions(context.Background(), "post-invalid-delete")
	if err != nil || count != 1 {
		t.Fatalf("invalid lifecycle fact mutated relations: count=%d err=%v", count, err)
	}
}

func postDeletedOutboxEvent(t *testing.T, postID, eventID string) postports.OutboxEvent {
	t.Helper()
	now := time.Now().UTC().Truncate(time.Millisecond)
	payload, err := json.Marshal(map[string]any{
		"_id":             postID,
		"authorId":        "post-owner",
		"contentType":     "image",
		"contentIdentity": "work",
		"status":          "published",
		"circleIds":       []string{},
		"deletedAt":       now.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	return postports.OutboxEvent{
		EventID:          eventID,
		EventType:        "PostDeleted",
		AggregateType:    "Post",
		AggregateID:      postID,
		AggregateVersion: 2,
		Payload:          payload,
		OccurredAt:       now,
	}
}
