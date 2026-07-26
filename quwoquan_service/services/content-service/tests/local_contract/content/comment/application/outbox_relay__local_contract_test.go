package comment_test

import (
	"context"
	"errors"
	"testing"

	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

type commentRelayPublisher struct {
	fail   bool
	events []commentports.OutboxEvent
}

func (p *commentRelayPublisher) Publish(_ context.Context, event commentports.OutboxEvent) error {
	if p.fail {
		return errors.New("publisher unavailable")
	}
	p.events = append(p.events, event)
	return nil
}

func TestCommentOutboxRelayRetriesWithoutAdvancingFailedCheckpoint(t *testing.T) {
	t.Parallel()
	store := commenttestsupport.NewStore()
	store.SeedPost("post-relay", "post-owner")
	service := commentapp.NewCommentService(commentapp.BindDataPorts(
		store,
		store,
		testsupport.NewReactionStore(),
		store,
		store,
	))
	if _, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-relay-create"),
		commentapp.CreateCommentCommand{
			PostID: "post-relay", ActorID: "comment-author", Content: "relay",
		},
	); err != nil {
		t.Fatal(err)
	}

	publisher := &commentRelayPublisher{fail: true}
	relay := commentapp.NewOutboxRelay(store, store, publisher, "comment-relay-test")
	if _, err := relay.Drain(context.Background(), 100); err == nil {
		t.Fatal("publisher failure must keep Comment outbox replayable")
	}
	checkpoint, err := store.LoadCheckpoint(context.Background(), "comment-relay-test")
	if err != nil || checkpoint != "" {
		t.Fatalf("failed relay advanced checkpoint=%q err=%v", checkpoint, err)
	}
	publisher.fail = false
	count, err := relay.Drain(context.Background(), 100)
	if err != nil || count != 1 || len(publisher.events) != 1 {
		t.Fatalf("retry count=%d published=%d err=%v", count, len(publisher.events), err)
	}
	checkpoint, err = store.LoadCheckpoint(context.Background(), "comment-relay-test")
	if err != nil || checkpoint == "" {
		t.Fatalf("successful relay checkpoint=%q err=%v", checkpoint, err)
	}
}

var _ commentports.OutboxPublisher = (*commentRelayPublisher)(nil)
