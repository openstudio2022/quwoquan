// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-011
package local_contract

import (
	"context"
	"errors"
	"testing"

	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

type staticCommentViewerBlockReader struct {
	blocked []string
	err     error
	calls   int
	viewer  string
}

func (r *staticCommentViewerBlockReader) ListBlockedPersonaIDs(
	_ context.Context,
	viewerPersonaID string,
) ([]string, error) {
	r.calls++
	r.viewer = viewerPersonaID
	if r.err != nil {
		return nil, r.err
	}
	return append([]string(nil), r.blocked...), nil
}

func TestCommentQueriesEnforceServerProjectedBlockFacts(t *testing.T) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-comment-block", "persona-post-owner")
	blocks := &staticCommentViewerBlockReader{
		blocked: []string{"persona-blocked-commenter"},
	}
	service := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			store,
			store,
			testsupport.NewReactionStore(),
			store,
			blocks,
		),
	)
	visible := createComment(
		t,
		service,
		"comment-visible-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-block",
			ActorID: "persona-visible-commenter",
			Content: "visible comment",
		},
	)
	createComment(
		t,
		service,
		"comment-blocked-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-block",
			ActorID: "persona-blocked-commenter",
			Content: "blocked comment",
		},
	)
	createComment(
		t,
		service,
		"comment-blocked-reply-create",
		commentapp.CreateCommentCommand{
			PostID:           "post-comment-block",
			ActorID:          "persona-blocked-commenter",
			Content:          "blocked reply",
			ReplyToCommentID: visible.ID,
		},
	)

	page, err := service.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID:  "post-comment-block",
		ActorID: "persona-viewer",
		Limit:   20,
	})
	if err != nil {
		t.Fatalf("ListComments: %v", err)
	}
	if blocks.calls != 1 || blocks.viewer != "persona-viewer" {
		t.Fatalf("server block projection was not queried for viewer: %+v", blocks)
	}
	if len(page.Items) != 1 || page.Items[0].ID != visible.ID {
		t.Fatalf("blocked commenter leaked into top-level comments: %+v", page)
	}
	if page.Items[0].ReplyCount != 0 ||
		len(page.Items[0].ReplyPreview) != 0 ||
		page.Items[0].ReplyNextCursor != "" {
		t.Fatalf("blocked reply leaked through reply summary: %+v", page.Items[0])
	}

	replies, err := service.ListReplies(
		context.Background(),
		commentapp.ListCommentRepliesQuery{
			PostID:          "post-comment-block",
			ParentCommentID: visible.ID,
			ActorID:         "persona-viewer",
			Limit:           20,
		},
	)
	if err != nil {
		t.Fatalf("ListReplies: %v", err)
	}
	if len(replies.Items) != 0 || replies.Total != 0 {
		t.Fatalf("blocked commenter leaked into reply page: %+v", replies)
	}
}

func TestCommentQueriesHideBlockedPostOwnerAndFailClosed(t *testing.T) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-owner-blocked", "persona-post-owner")
	blocks := &staticCommentViewerBlockReader{
		blocked: []string{"persona-post-owner"},
	}
	service := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			store,
			store,
			testsupport.NewReactionStore(),
			store,
			blocks,
		),
	)
	createComment(
		t,
		service,
		"comment-owner-block-create",
		commentapp.CreateCommentCommand{
			PostID:  "post-owner-blocked",
			ActorID: "persona-commenter",
			Content: "must stay hidden with its post",
		},
	)

	page, err := service.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID:  "post-owner-blocked",
		ActorID: "persona-viewer",
	})
	if err != nil {
		t.Fatalf("blocked post owner must produce an empty comment page: %v", err)
	}
	if len(page.Items) != 0 || page.Total != 0 {
		t.Fatalf("blocked post owner's comments leaked: %+v", page)
	}

	blocks.blocked = nil
	blocks.err = errors.New("block projection unavailable")
	if _, err = service.ListComments(
		context.Background(),
		commentapp.ListCommentsQuery{
			PostID:  "post-owner-blocked",
			ActorID: "persona-viewer",
		},
	); err == nil {
		t.Fatal("comment read must fail closed when block facts cannot be read")
	}
}
