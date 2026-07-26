// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-012
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-013
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/comment"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
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

func TestBindMediaAssetsToCommentIsOwnerScopedAndIdempotent(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(
		t,
		service,
		"comment-bind-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-owner",
			ActorID: "persona-comment-author",
			Content: "绑定附件的评论",
		},
	)
	command := commentapp.BindCommentAttachmentsCommand{
		CommentID:          created.ID,
		ActorID:            "persona-comment-author",
		AttachmentMediaIDs: []string{"media-1", "media-2"},
	}
	ctx := commandmeta.WithIdempotencyKey(
		context.Background(),
		"comment-bind-media",
	)
	bound, err := service.BindAttachments(ctx, command)
	if err != nil {
		t.Fatalf("bind comment attachments: %v", err)
	}
	replayed, err := service.BindAttachments(ctx, command)
	if err != nil {
		t.Fatalf("replay bind comment attachments: %v", err)
	}
	if !replayed.Replayed || replayed.Version != bound.Version {
		t.Fatalf("bind replay must return original receipt: bound=%+v replayed=%+v", bound, replayed)
	}
	page, err := service.ListComments(
		context.Background(),
		commentapp.ListCommentsQuery{PostID: "post-comment-owner", Limit: 20},
	)
	if err != nil {
		t.Fatalf("list bound comment: %v", err)
	}
	if len(page.Items) != 1 ||
		len(page.Items[0].AttachmentMediaIDs) != 2 ||
		page.Items[0].AttachmentMediaIDs[0] != "media-1" {
		t.Fatalf("bound media assets must be visible through typed reader: %+v", page)
	}
	outbox := store.OutboxEvents()
	if len(outbox) != 2 || outbox[1].EventType != "CommentAttachmentsBound" {
		t.Fatalf("bind must emit one canonical event and replay none: %+v", outbox)
	}
	_, err = service.BindAttachments(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-bind-denied"),
		commentapp.BindCommentAttachmentsCommand{
			CommentID:          created.ID,
			ActorID:            "persona-intruder",
			AttachmentMediaIDs: []string{"media-3"},
		},
	)
	if err == nil {
		t.Fatal("non-owner must not bind attachments to Comment")
	}
}

func TestCommentRejectsMoreThanNineAttachments(t *testing.T) {
	service, _ := newCommentAggregateService()
	overLimit := []string{
		"media-1",
		"media-2",
		"media-3",
		"media-4",
		"media-5",
		"media-6",
		"media-7",
		"media-8",
		"media-9",
		"media-10",
	}
	_, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-attachment-limit-create"),
		commentapp.CreateCommentCommand{
			PostID:             "post-comment-owner",
			ActorID:            "persona-comment-author",
			Content:            "附件数超限",
			AttachmentMediaIDs: overLimit,
		},
	)
	if err == nil {
		t.Fatal("CreateComment must reject more than nine attachment media IDs")
	}
	assertCommentRuntimeErrorCode(
		t,
		err,
		contentgenerated.AppErrorFromCommentAttachmentLimitExceeded(""),
	)

	created := createComment(
		t,
		service,
		"comment-attachment-limit-bind-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-owner",
			ActorID: "persona-comment-author",
			Content: "绑定附件数超限",
		},
	)
	_, err = service.BindAttachments(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-attachment-limit-bind"),
		commentapp.BindCommentAttachmentsCommand{
			CommentID:          created.ID,
			ActorID:            "persona-comment-author",
			AttachmentMediaIDs: overLimit,
		},
	)
	if err == nil {
		t.Fatal("BindAttachments must reject more than nine attachment media IDs")
	}
	assertCommentRuntimeErrorCode(
		t,
		err,
		contentgenerated.AppErrorFromCommentAttachmentLimitExceeded(""),
	)
}

func TestHideCommentModerationLifecycle(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(
		t,
		service,
		"comment-hide-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-owner",
			ActorID: "persona-comment-author",
			Content: "等待治理隐藏的评论",
		},
	)
	ctx := commandmeta.WithIdempotencyKey(
		context.Background(),
		"comment-hide-command",
	)
	command := commentapp.HideCommentCommand{
		CommentID:  created.ID,
		OperatorID: "operator-comment-moderation",
		Reason:     "confirmed abuse",
	}
	hidden, err := service.HideComment(ctx, command)
	if err != nil {
		t.Fatalf("hide Comment: %v", err)
	}
	if hidden.Status != commentmodel.StatusHidden ||
		hidden.Version != created.Version+1 ||
		hidden.Replayed {
		t.Fatalf("unexpected hidden Comment result: %+v", hidden)
	}
	aggregate, found, err := store.Load(context.Background(), created.ID)
	if err != nil || !found {
		t.Fatalf("load hidden Comment: found=%v err=%v", found, err)
	}
	snapshot := aggregate.Snapshot()
	if snapshot.Status != commentmodel.StatusHidden ||
		snapshot.HiddenAt == nil ||
		snapshot.IsPinned ||
		snapshot.PinnedAt != nil {
		t.Fatalf("hidden Comment snapshot is inconsistent: %+v", snapshot)
	}
	count, err := store.CountByPost(context.Background(), "post-comment-owner")
	if err != nil || count != 0 {
		t.Fatalf("hidden Comment must leave the active count: count=%d err=%v", count, err)
	}
	page, err := service.ListComments(
		context.Background(),
		commentapp.ListCommentsQuery{PostID: "post-comment-owner"},
	)
	if err != nil || len(page.Items) != 0 || page.Total != 0 {
		t.Fatalf("hidden Comment leaked into active page: page=%+v err=%v", page, err)
	}
	ownPage, err := service.ListByAuthor(
		context.Background(),
		commentapp.ListCommentsByAuthorQuery{ActorID: "persona-comment-author"},
	)
	if err != nil ||
		len(ownPage.Items) != 1 ||
		ownPage.Items[0].ID != created.ID ||
		ownPage.Items[0].Status != commentmodel.StatusHidden {
		t.Fatalf(
			"hidden Comment must remain visible in its author's private projection: page=%+v err=%v",
			ownPage,
			err,
		)
	}

	replayed, err := service.HideComment(ctx, command)
	if err != nil {
		t.Fatalf("replay HideComment: %v", err)
	}
	if !replayed.Replayed ||
		replayed.Version != hidden.Version ||
		replayed.Status != commentmodel.StatusHidden {
		t.Fatalf("HideComment replay did not return the original receipt: %+v", replayed)
	}
	if _, err := service.HideComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-hide-illegal"),
		command,
	); err == nil {
		t.Fatal("a second HideComment intent from hidden state must be rejected")
	} else {
		assertCommentRuntimeErrorCode(
			t,
			err,
			contentgenerated.AppErrorFromCommentStatusTransitionInvalid(""),
		)
	}

	outbox := store.OutboxEvents()
	if len(outbox) != 2 || outbox[1].EventType != "CommentModerated" {
		t.Fatalf("HideComment must append one CommentModerated fact: %+v", outbox)
	}
	var payload struct {
		CommentID  string    `json:"commentId"`
		Version    int64     `json:"version"`
		PostID     string    `json:"postId"`
		OperatorID string    `json:"operatorId"`
		Action     string    `json:"action"`
		Reason     string    `json:"reason"`
		OccurredAt time.Time `json:"occurredAt"`
	}
	if err := json.Unmarshal(outbox[1].Payload, &payload); err != nil {
		t.Fatalf("decode CommentModerated payload: %v", err)
	}
	if payload.CommentID != created.ID ||
		payload.Version != hidden.Version ||
		payload.PostID != "post-comment-owner" ||
		payload.OperatorID != command.OperatorID ||
		payload.Action != "hide" ||
		payload.Reason != command.Reason ||
		payload.OccurredAt.IsZero() {
		t.Fatalf("HideComment audit payload drifted: %+v", payload)
	}
}

func TestRestoreCommentModerationLifecycle(t *testing.T) {
	service, store := newCommentAggregateService()
	created := createComment(
		t,
		service,
		"comment-restore-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-owner",
			ActorID: "persona-comment-author",
			Content: "等待治理恢复的评论",
		},
	)
	if _, err := service.HideComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-restore-hide"),
		commentapp.HideCommentCommand{
			CommentID:  created.ID,
			OperatorID: "operator-comment-moderation",
			Reason:     "temporary hold",
		},
	); err != nil {
		t.Fatalf("prepare hidden Comment: %v", err)
	}
	ctx := commandmeta.WithIdempotencyKey(
		context.Background(),
		"comment-restore-command",
	)
	command := commentapp.RestoreCommentCommand{
		CommentID:  created.ID,
		OperatorID: "operator-comment-moderation",
		Reason:     "review cleared",
	}
	restored, err := service.RestoreComment(ctx, command)
	if err != nil {
		t.Fatalf("restore Comment: %v", err)
	}
	if restored.Status != commentmodel.StatusActive ||
		restored.Version != created.Version+2 ||
		restored.Replayed {
		t.Fatalf("unexpected restored Comment result: %+v", restored)
	}
	aggregate, found, err := store.Load(context.Background(), created.ID)
	if err != nil || !found {
		t.Fatalf("load restored Comment: found=%v err=%v", found, err)
	}
	if snapshot := aggregate.Snapshot(); snapshot.HiddenAt != nil ||
		snapshot.Status != commentmodel.StatusActive {
		t.Fatalf("RestoreComment must clear hidden state: %+v", snapshot)
	}
	count, err := store.CountByPost(context.Background(), "post-comment-owner")
	if err != nil || count != 1 {
		t.Fatalf("restored Comment must re-enter the active count: count=%d err=%v", count, err)
	}

	replayed, err := service.RestoreComment(ctx, command)
	if err != nil {
		t.Fatalf("replay RestoreComment: %v", err)
	}
	if !replayed.Replayed ||
		replayed.Version != restored.Version ||
		replayed.Status != commentmodel.StatusActive {
		t.Fatalf("RestoreComment replay did not return the original receipt: %+v", replayed)
	}
	if _, err := service.RestoreComment(
		commandmeta.WithIdempotencyKey(context.Background(), "comment-restore-illegal"),
		command,
	); err == nil {
		t.Fatal("a second RestoreComment intent from active state must be rejected")
	} else {
		assertCommentRuntimeErrorCode(
			t,
			err,
			contentgenerated.AppErrorFromCommentStatusTransitionInvalid(""),
		)
	}

	now := time.Now().UTC()
	deleted, err := commentmodel.Create(commentmodel.CreateParams{
		ID: "comment-terminal-deleted", PostID: "post-comment-owner",
		AuthorID: "persona-comment-author", Content: "deleted terminal", Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := deleted.Delete("persona-comment-author", now.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := deleted.Hide("operator-comment-moderation", now.Add(2*time.Second)); !errors.Is(
		err,
		commentmodel.ErrInvalidStatusTransition,
	) {
		t.Fatalf("deleted Comment accepted HideComment: %v", err)
	}
	if err := deleted.RestoreFromHidden("operator-comment-moderation", now.Add(2*time.Second)); !errors.Is(
		err,
		commentmodel.ErrInvalidStatusTransition,
	) {
		t.Fatalf("deleted Comment accepted RestoreComment: %v", err)
	}
	tombstoned, err := commentmodel.Restore(commentmodel.Snapshot{
		ID: "comment-terminal-tombstoned", Version: 3,
		PostID: "post-comment-owner", AuthorID: "persona-comment-author",
		Content: "tombstoned terminal", Status: commentmodel.StatusTombstoned,
		CreatedAt: now, UpdatedAt: now.Add(time.Second),
	})
	if err != nil {
		t.Fatalf("restore tombstoned Comment snapshot: %v", err)
	}
	if err := tombstoned.Hide("operator-comment-moderation", now.Add(2*time.Second)); !errors.Is(
		err,
		commentmodel.ErrInvalidStatusTransition,
	) {
		t.Fatalf("tombstoned Comment accepted HideComment: %v", err)
	}
	if err := tombstoned.RestoreFromHidden("operator-comment-moderation", now.Add(2*time.Second)); !errors.Is(
		err,
		commentmodel.ErrInvalidStatusTransition,
	) {
		t.Fatalf("tombstoned Comment accepted RestoreComment: %v", err)
	}

	outbox := store.OutboxEvents()
	if len(outbox) != 3 ||
		outbox[1].EventType != "CommentModerated" ||
		outbox[2].EventType != "CommentModerated" {
		t.Fatalf("restore lifecycle facts drifted: %+v", outbox)
	}
	var payload struct {
		Action     string `json:"action"`
		Reason     string `json:"reason"`
		OperatorID string `json:"operatorId"`
	}
	if err := json.Unmarshal(outbox[2].Payload, &payload); err != nil {
		t.Fatalf("decode restored CommentModerated payload: %v", err)
	}
	if payload.Action != "restore" ||
		payload.Reason != command.Reason ||
		payload.OperatorID != command.OperatorID {
		t.Fatalf("RestoreComment audit payload drifted: %+v", payload)
	}
}

func TestCommentModerationSnapshotValidation(t *testing.T) {
	now := time.Now().UTC()
	base := commentmodel.Snapshot{
		ID:        "comment-moderation-snapshot",
		Version:   2,
		PostID:    "post-comment-owner",
		AuthorID:  "persona-comment-author",
		Content:   "moderation snapshot validation",
		CreatedAt: now,
		UpdatedAt: now.Add(time.Second),
	}
	hiddenWithoutTimestamp := base
	hiddenWithoutTimestamp.Status = commentmodel.StatusHidden
	if _, err := commentmodel.Restore(hiddenWithoutTimestamp); err == nil {
		t.Fatal("hidden Comment snapshot without hiddenAt must be rejected")
	}
	activeWithHiddenTimestamp := base
	activeWithHiddenTimestamp.Status = commentmodel.StatusActive
	activeWithHiddenTimestamp.HiddenAt = cloneCommentTestTime(now.Add(time.Second))
	if _, err := commentmodel.Restore(activeWithHiddenTimestamp); err == nil {
		t.Fatal("active Comment snapshot retaining hiddenAt must be rejected")
	}
	deletedWithoutTimestamp := base
	deletedWithoutTimestamp.Status = commentmodel.StatusDeleted
	if _, err := commentmodel.Restore(deletedWithoutTimestamp); err == nil {
		t.Fatal("deleted Comment snapshot without deletedAt must be rejected")
	}
}

func newCommentAggregateService() (*commentapp.CommentService, *commenttestsupport.Store) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-comment-owner", "persona-post-owner")
	return commentapp.NewCommentService(commentapp.BindDataPorts(
		store,
		store,
		testsupport.NewReactionStore(),
		store,
		store,
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

func cloneCommentTestTime(value time.Time) *time.Time {
	cloned := value.UTC()
	return &cloned
}

func assertCommentRuntimeErrorCode(
	t *testing.T,
	err error,
	want *rterr.AppError,
) {
	t.Helper()
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("expected Runtime AppError, got %T: %v", err, err)
	}
	if appError.Code.String() != want.Code.String() {
		t.Fatalf(
			"Runtime error code=%q want=%q",
			appError.Code.String(),
			want.Code.String(),
		)
	}
}
