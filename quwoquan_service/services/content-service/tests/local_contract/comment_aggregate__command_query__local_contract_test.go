package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	"quwoquan_service/services/content-service/internal/testsupport"
	commenttestsupport "quwoquan_service/services/content-service/internal/testsupport/comment"
)

func TestCommentAggregateRejectsNonOwnerDeleteAndPin(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(t, service, "comment-owner-create", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-comment-author",
		Content: "第一条评论",
	})

	_, err := service.DeleteComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-owner-delete-denied"),
		commentapp.DeleteCommentCommand{
			PostID:    "post-comment-owner",
			CommentID: created.ID,
			ActorID:   "persona-intruder",
		},
	)
	if err == nil {
		t.Fatal("non-owner delete must be rejected")
	}
	aggregate, found, loadErr := store.Load(context.Background(), created.ID)
	if loadErr != nil || !found || aggregate.Status() != commentmodel.StatusActive {
		t.Fatalf("denied delete must preserve active aggregate: found=%v status=%v err=%v", found, aggregate.Status(), loadErr)
	}

	_, err = service.PinComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-owner-pin-denied"),
		commentapp.ChangeCommentPinCommand{
			PostID:    "post-comment-owner",
			CommentID: created.ID,
			ActorID:   "persona-intruder",
		},
	)
	if err == nil {
		t.Fatal("non-post-owner pin must be rejected")
	}
	aggregate, found, loadErr = store.Load(context.Background(), created.ID)
	if loadErr != nil || !found || aggregate.Version() != created.Version {
		t.Fatalf("denied pin must not advance aggregate: found=%v version=%d err=%v", found, aggregate.Version(), loadErr)
	}
}

func TestCommentAggregateIdempotencyDoesNotDuplicateFact(t *testing.T) {
	service, store := newCommentAggregateService()
	command := commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-comment-author",
		Content: "幂等评论",
	}
	ctx := commandmeta.WithIdempotencyKey(context.Background(), "comment-idempotency-create")
	created, err := service.CreateComment(ctx, command)
	if err != nil {
		t.Fatalf("create comment: %v", err)
	}
	replayed, err := service.CreateComment(ctx, command)
	if err != nil {
		t.Fatalf("replay comment create: %v", err)
	}
	if !replayed.Replayed ||
		replayed.ID != created.ID ||
		replayed.Version != created.Version {
		t.Fatalf("unexpected replay result: created=%+v replayed=%+v", created, replayed)
	}
	count, err := store.CountByPost(context.Background(), "post-comment-owner")
	if err != nil {
		t.Fatalf("count comments: %v", err)
	}
	if count != 1 {
		t.Fatalf("idempotent create must persist one comment, got %d", count)
	}
	outbox := store.OutboxEvents()
	if len(outbox) != 1 {
		t.Fatalf("idempotent create must persist one fact, got %d", len(outbox))
	}
	if outbox[0].AggregateID != created.ID ||
		outbox[0].AggregateVersion != created.Version {
		t.Fatalf("outbox fact must match committed version: %+v result=%+v", outbox[0], created)
	}

	_, err = service.CreateComment(ctx, commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-comment-author",
		Content: "相同幂等键但不同内容",
	})
	if err == nil {
		t.Fatal("same actor cannot reuse an idempotency key with another digest")
	}
	count, err = store.CountByPost(context.Background(), "post-comment-owner")
	if err != nil {
		t.Fatalf("count comments after digest conflict: %v", err)
	}
	if count != 1 || len(store.OutboxEvents()) != 1 {
		t.Fatalf("digest conflict must not mutate comment or outbox: count=%d facts=%d", count, len(store.OutboxEvents()))
	}
}

func TestCommentNoopIntentPersistsReceiptBeforeLaterStateChange(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(
		t,
		service,
		"comment-noop-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-owner",
			ActorID: "persona-comment-author",
			Content: "幂等 no-op 评论",
		},
	)
	pin := commentapp.ChangeCommentPinCommand{
		PostID:    "post-comment-owner",
		CommentID: created.ID,
		ActorID:   "persona-post-owner",
	}
	if _, err := service.PinComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-pin-first"),
		pin,
	); err != nil {
		t.Fatalf("pin comment: %v", err)
	}
	noopContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"comment-pin-noop",
	)
	noop, err := service.PinComment(noopContext, pin)
	if err != nil {
		t.Fatalf("record pin no-op: %v", err)
	}
	if noop.Replayed || noop.Version != created.Version+1 {
		t.Fatalf("first no-op must persist its current result: %+v", noop)
	}
	if _, err := service.UnpinComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-unpin"),
		pin,
	); err != nil {
		t.Fatalf("unpin comment: %v", err)
	}
	replayed, err := service.PinComment(noopContext, pin)
	if err != nil {
		t.Fatalf("replay pin no-op: %v", err)
	}
	if !replayed.Replayed || replayed.Version != noop.Version {
		t.Fatalf("no-op retry must replay its original result: %+v", replayed)
	}
	aggregate, found, err := store.Load(context.Background(), created.ID)
	if err != nil || !found || aggregate.Snapshot().IsPinned {
		t.Fatalf(
			"no-op replay must not overwrite the later unpin: found=%v snapshot=%+v err=%v",
			found,
			aggregate.Snapshot(),
			err,
		)
	}
}

func TestCommentAggregateScopesReceiptAndPrivateReadersToActor(t *testing.T) {
	service, _ := newCommentAggregateService()
	first := createComment(t, service, "shared-external-idempotency-key", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-comment-author",
		Content: "作者自己的评论",
	})
	second := createComment(t, service, "shared-external-idempotency-key", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-second-author",
		Content: "另一位作者的评论",
	})
	if first.ID == second.ID || second.Replayed {
		t.Fatalf("idempotency receipts must be actor-scoped: first=%+v second=%+v", first, second)
	}

	ownPage, err := service.ListByAuthor(context.Background(), commentapp.ListCommentsByAuthorQuery{
		ActorID: "persona-comment-author",
	})
	if err != nil {
		t.Fatalf("list own comments: %v", err)
	}
	if len(ownPage.Items) != 1 || ownPage.Items[0].ID != first.ID {
		t.Fatalf("author reader must only return the caller's comments: %+v", ownPage)
	}
	otherPage, err := service.ListByAuthor(context.Background(), commentapp.ListCommentsByAuthorQuery{
		ActorID: "persona-second-author",
	})
	if err != nil {
		t.Fatalf("list second author's comments: %v", err)
	}
	if len(otherPage.Items) != 1 || otherPage.Items[0].ID != second.ID {
		t.Fatalf("author reader must not disclose another actor's comments: %+v", otherPage)
	}
	if _, err := service.ListByAuthor(context.Background(), commentapp.ListCommentsByAuthorQuery{}); err == nil {
		t.Fatal("private author reader must require an actor")
	}

	received, err := service.ListReceivedByPostAuthor(context.Background(), commentapp.ListReceivedCommentsQuery{
		ActorID: "persona-post-owner",
	})
	if err != nil {
		t.Fatalf("list received comments: %v", err)
	}
	if len(received.Items) != 2 {
		t.Fatalf("post owner must receive comments for owned posts only: %+v", received)
	}
	none, err := service.ListReceivedByPostAuthor(context.Background(), commentapp.ListReceivedCommentsQuery{
		ActorID: "persona-unrelated",
	})
	if err != nil {
		t.Fatalf("list unrelated actor received comments: %v", err)
	}
	if len(none.Items) != 0 {
		t.Fatalf("unrelated actor must not enumerate another post owner's comments: %+v", none)
	}
	if _, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "missing-actor"),
		commentapp.CreateCommentCommand{PostID: "post-comment-owner", Content: "冒名评论"},
	); err == nil {
		t.Fatal("create comment must require an actor instead of accepting caller-supplied author identity")
	}
}

func TestCommentAggregateExpiresReceiptWithoutRemovingCommittedFact(t *testing.T) {
	store := commenttestsupport.NewStore()
	now := time.Now().UTC()
	aggregate, err := commentmodel.Create(commentmodel.CreateParams{
		ID:       "comment-expired-receipt",
		PostID:   "post-comment-owner",
		AuthorID: "persona-comment-author",
		Content:  "已过期回执",
		Now:      now,
	})
	if err != nil {
		t.Fatalf("create aggregate: %v", err)
	}
	_, err = store.Commit(context.Background(), commentports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  0,
		IdempotencyKey:   "expired-comment-receipt",
		CommandName:      "CreateComment",
		CommandDigest:    "digest-expired-comment-receipt",
		ReceiptExpiresAt: now.Add(-time.Second),
		Events: []commentports.OutboxEvent{{
			EventID:          "event-expired-comment-receipt",
			EventType:        "CommentCreated",
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          []byte(`{"commentId":"comment-expired-receipt"}`),
			OccurredAt:       now,
		}},
	})
	if err != nil {
		t.Fatalf("commit expired receipt: %v", err)
	}
	_, found, err := store.FindReceipt(
		context.Background(),
		"expired-comment-receipt",
		"CreateComment",
		"digest-expired-comment-receipt",
	)
	if err != nil {
		t.Fatalf("find expired receipt: %v", err)
	}
	if found {
		t.Fatal("expired receipt must not be replayed")
	}
	count, err := store.CountByPost(context.Background(), "post-comment-owner")
	if err != nil {
		t.Fatalf("count aggregate after receipt expiry: %v", err)
	}
	if count != 1 || len(store.OutboxEvents()) != 1 {
		t.Fatalf("receipt expiry must preserve committed aggregate and outbox fact: count=%d facts=%d", count, len(store.OutboxEvents()))
	}
}

func TestCommentAggregateAppliesIntentAgainstLatestVersion(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(t, service, "comment-version-create", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-comment-author",
		Content: "并发版本",
	})
	pinned, err := service.PinComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-version-pin"),
		commentapp.ChangeCommentPinCommand{
			PostID:    "post-comment-owner",
			CommentID: created.ID,
			ActorID:   "persona-post-owner",
		},
	)
	if err != nil {
		t.Fatalf("pin comment: %v", err)
	}
	if pinned.Version != created.Version+1 {
		t.Fatalf("pin must advance version: %+v", pinned)
	}
	deleted, err := service.DeleteComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-version-delete"),
		commentapp.DeleteCommentCommand{
			PostID:    "post-comment-owner",
			CommentID: created.ID,
			ActorID:   "persona-comment-author",
		},
	)
	if err != nil {
		t.Fatalf("delete latest Comment intent: %v", err)
	}
	aggregate, found, loadErr := store.Load(context.Background(), created.ID)
	if loadErr != nil || !found ||
		aggregate.Version() != pinned.Version+1 ||
		aggregate.Status() != commentmodel.StatusDeleted ||
		deleted.Version != aggregate.Version() {
		t.Fatalf("server-owned CAS must commit the latest intent: found=%v version=%d status=%s result=%+v err=%v", found, aggregate.Version(), aggregate.Status(), deleted, loadErr)
	}
}

func TestCommentAggregateEmitsCanonicalPostProjectionFacts(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(t, service, "comment-fact-create", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-comment-author",
		Content: "用于投影的评论",
	})
	deleted, err := service.DeleteComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-fact-delete"),
		commentapp.DeleteCommentCommand{
			PostID:    "post-comment-owner",
			CommentID: created.ID,
			ActorID:   "persona-comment-author",
		},
	)
	if err != nil {
		t.Fatalf("delete Comment: %v", err)
	}
	outbox := store.OutboxEvents()
	if len(outbox) != 2 {
		t.Fatalf("want one creation and one deletion fact, got %+v", outbox)
	}
	if outbox[0].EventType != "CommentCreated" ||
		outbox[1].EventType != "CommentDeleted" {
		t.Fatalf("Post comment-count projection may consume only canonical Comment facts: %+v", outbox)
	}
	if outbox[0].AggregateVersion != created.Version ||
		outbox[1].AggregateVersion != deleted.Version {
		t.Fatalf("canonical Comment facts must retain committed versions: %+v", outbox)
	}
}

func TestCommentAggregateNormalizesTwoLevelReplyInvariant(t *testing.T) {
	service, store := newCommentAggregateService()
	store.SeedPost("post-comment-other", "persona-other-post-owner")
	parent := createComment(t, service, "comment-parent-create", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-parent",
		Content: "一级评论",
	})
	reply := createComment(t, service, "comment-reply-create", commentapp.CreateCommentCommand{
		PostID:           "post-comment-owner",
		ActorID:          "persona-reply",
		Content:          "回复一级",
		ReplyToCommentID: parent.ID,
	})
	nestedReply := createComment(t, service, "comment-nested-reply-create", commentapp.CreateCommentCommand{
		PostID:           "post-comment-owner",
		ActorID:          "persona-nested-reply",
		Content:          "回复二级",
		ReplyToCommentID: reply.ID,
	})
	target, found, err := store.FindReplyTarget(context.Background(), nestedReply.ID)
	if err != nil || !found {
		t.Fatalf("load normalized reply target: found=%v err=%v", found, err)
	}
	if target.ParentCommentID != parent.ID {
		t.Fatalf("reply-to-reply must stay in root thread: parent=%q want=%q", target.ParentCommentID, parent.ID)
	}

	_, err = service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-cross-post-reply"),
		commentapp.CreateCommentCommand{
			PostID:           "post-comment-other",
			ActorID:          "persona-cross-post",
			Content:          "跨内容回复",
			ReplyToCommentID: parent.ID,
		},
	)
	if err == nil {
		t.Fatal("reply target from another post must be rejected")
	}
	count, countErr := store.CountByPost(context.Background(), "post-comment-other")
	if countErr != nil || count != 0 {
		t.Fatalf("rejected cross-post reply must not persist: count=%d err=%v", count, countErr)
	}
}

func TestCommentReadersReturnDetachedTypedSlicesAndFactsMatchCommit(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(t, service, "comment-reader-create", commentapp.CreateCommentCommand{
		PostID:             "post-comment-owner",
		ActorID:            "persona-comment-author",
		Content:            "有附件的评论",
		AttachmentMediaIDs: []string{"media-original"},
	})
	pinned, err := service.PinComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-reader-pin"),
		commentapp.ChangeCommentPinCommand{
			PostID:    "post-comment-owner",
			CommentID: created.ID,
			ActorID:   "persona-post-owner",
		},
	)
	if err != nil {
		t.Fatalf("pin comment: %v", err)
	}

	page, err := service.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID: "post-comment-owner",
		Limit:  20,
	})
	if err != nil {
		t.Fatalf("list comment page: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].ID != created.ID {
		t.Fatalf("reader must return one typed comment item: %+v", page)
	}
	page.Items[0].AttachmentMediaIDs[0] = "mutated-by-caller"
	again, err := service.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID: "post-comment-owner",
		Limit:  20,
	})
	if err != nil {
		t.Fatalf("list comment page again: %v", err)
	}
	if again.Items[0].AttachmentMediaIDs[0] != "media-original" {
		t.Fatalf("reader slice must be detached from stored aggregate: %+v", again.Items[0])
	}

	outbox := store.OutboxEvents()
	if len(outbox) != 2 {
		t.Fatalf("want create and pin facts, got %d", len(outbox))
	}
	if outbox[0].EventType != "CommentCreated" ||
		outbox[1].EventType != "CommentPinChanged" {
		t.Fatalf("outbox must use canonical metadata event names: %+v", outbox)
	}
	for _, event := range outbox {
		if event.AggregateID != created.ID {
			t.Fatalf("outbox fact aggregate id mismatch: %+v", event)
		}
	}
	if outbox[0].AggregateVersion != created.Version ||
		outbox[1].AggregateVersion != pinned.Version {
		t.Fatalf("outbox commit versions must stay aligned: %+v pinned=%+v", outbox, pinned)
	}
}

func newCommentAggregateService() (*commentapp.CommentService, *commenttestsupport.Store) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-comment-owner", "persona-post-owner")
	return commentapp.NewCommentService(commentapp.BindDataPorts(
		store,
		store,
		testsupport.NewReactionStore(),
	)), store
}

func createComment(
	t *testing.T,
	service *commentapp.CommentService,
	idempotencyKey string,
	command commentapp.CreateCommentCommand,
) commentapp.CommentCommandResult {
	t.Helper()
	result, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), idempotencyKey),
		command,
	)
	if err != nil {
		t.Fatalf("create comment: %v", err)
	}
	return result
}
