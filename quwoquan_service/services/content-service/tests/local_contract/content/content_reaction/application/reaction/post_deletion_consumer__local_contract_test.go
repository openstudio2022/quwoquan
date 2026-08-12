package reaction_test

import (
	"context"
	"encoding/json"
	"strconv"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
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

func TestReleaseImportPostDeletionFactPassesStrictConsumerAndAdvancesIndependently(
	t *testing.T,
) {
	t.Parallel()
	store := testsupport.NewReactionStore()
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, store))
	snapshots := make([]releaseimport.ImportedPostDeletionSnapshot, 0, 4)
	for index := range 4 {
		postID := "data_post_tombstone_" + string(rune('a'+index))
		actor := mustReactionActor(
			t,
			reactiondomain.ActorDimensionPersona,
			"persona-release-delete-"+string(rune('a'+index)),
		)
		if _, err := service.LikePost(
			commandmeta.WithIdempotencyKey(
				context.Background(),
				"release-delete-like-"+string(rune('a'+index)),
			),
			reactionapp.LikePostCommand{PostID: postID, Actor: actor},
		); err != nil {
			t.Fatal(err)
		}
		snapshots = append(snapshots, releaseimport.ImportedPostDeletionSnapshot{
			PostID: postID, AuthorID: "data-author-a", ContentType: "image",
			ContentIdentity: "work", Status: "published",
		})
	}
	now := time.Date(2026, 8, 11, 3, 10, 0, 0, time.UTC)
	events, err := releaseimport.BuildImportedPostLifecycleEvents(
		nil,
		snapshots,
		releaseimport.ImportOptions{
			ReleaseID:         "content-alpha-research-pool-20260811-002",
			ManifestDigest:    "sha256:58895c715e2547414c302b463e683b9878a2f441de7c2642194a5b3329ef83e0",
			SourceOwner:       "qwq_data",
			ProjectionVersion: 1786417850129,
		},
		now,
	)
	if err != nil {
		t.Fatalf("build release deletion: %v", err)
	}
	if len(events) != 4 {
		t.Fatalf("deletion events=%d, want 4", len(events))
	}
	consumer := reactionapp.NewPostDeletionConsumer(service, store)
	relayStore := &deletionRelayStore{
		checkpoints: map[string]string{},
		events:      append([]postports.OutboxEvent(nil), events...),
	}
	for index := range relayStore.events {
		relayStore.events[index].Checkpoint = strconv.Itoa(index + 47)
	}
	relay := postapp.NewOutboxRelay(
		relayStore,
		relayStore,
		consumer,
		"content-reaction-post-deletion",
	)
	if drained, err := relay.Drain(context.Background(), 10); err != nil || drained != 4 {
		t.Fatalf("drain canonical release deletions: drained=%d err=%v", drained, err)
	}
	if got := relayStore.checkpoints["content-reaction-post-deletion"]; got != "50" {
		t.Fatalf("deletion checkpoint=%q, want 50", got)
	}
	if drained, err := relay.Drain(context.Background(), 10); err != nil || drained != 0 {
		t.Fatalf("replayed drain: drained=%d err=%v", drained, err)
	}
	for _, snapshot := range snapshots {
		count, err := store.CountActiveReactions(context.Background(), snapshot.PostID)
		if err != nil || count != 0 {
			t.Fatalf(
				"release deletion %s did not advance independently: count=%d err=%v",
				snapshot.PostID,
				count,
				err,
			)
		}
	}
}

type deletionRelayStore struct {
	events      []postports.OutboxEvent
	checkpoints map[string]string
}

func (s *deletionRelayStore) ReadAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]postports.OutboxEvent, error) {
	start := 0
	if checkpoint != "" {
		start = len(s.events)
		for index, event := range s.events {
			if event.Checkpoint == checkpoint {
				start = index + 1
				break
			}
		}
	}
	end := len(s.events)
	if limit > 0 && start+limit < end {
		end = start + limit
	}
	return append([]postports.OutboxEvent(nil), s.events[start:end]...), nil
}

func (s *deletionRelayStore) LoadCheckpoint(
	_ context.Context,
	consumer string,
) (string, error) {
	return s.checkpoints[consumer], nil
}

func (s *deletionRelayStore) SaveCheckpoint(
	_ context.Context,
	consumer string,
	checkpoint string,
) error {
	s.checkpoints[consumer] = checkpoint
	return nil
}

func postDeletedOutboxEvent(t *testing.T, postID, eventID string) postports.OutboxEvent {
	t.Helper()
	now := time.Now().UTC().Truncate(time.Millisecond)
	payload, err := json.Marshal(map[string]any{
		"postId":          postID,
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
