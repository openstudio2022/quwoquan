// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// Comment 对象声明错误码的负例断言：每个用例真实驱动 application 拒绝路径
// 到 generated AppError 工厂的 emit 点，并以字面 wire code 锁定端云契约。
package comment_test

import (
	"context"
	"errors"
	"testing"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	posttestsupport "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

func newCommentErrorSemanticsService() (*commentapp.CommentService, *commenttestsupport.Store) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-err-sem", "persona-post-owner")
	return commentapp.NewCommentService(commentapp.BindDataPorts(
		store,
		store,
		posttestsupport.NewReactionStore(),
		store,
		store,
	)), store
}

func requireCommentAppErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected AppError %s, got nil", wantCode)
	}
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected *AppError %s, got %v", wantCode, err)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, appErr.Code.String())
	}
}

func createErrSemComment(
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

func TestDeleteCommentUnknownIDEmitsCommentNotFound(t *testing.T) {
	service, _ := newCommentErrorSemanticsService()
	_, err := service.DeleteComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-delete-unknown"),
		commentapp.DeleteCommentCommand{
			PostID: "post-err-sem", CommentID: "comment-missing", ActorID: "persona-author",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_not_found")
}

func TestDeleteCommentByNonAuthorEmitsCommentForbiddenDelete(t *testing.T) {
	service, _ := newCommentErrorSemanticsService()
	created := createErrSemComment(t, service, "err-sem-forbidden-create", commentapp.CreateCommentCommand{
		PostID: "post-err-sem", ActorID: "persona-author", Content: "作者本人的评论",
	})
	_, err := service.DeleteComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-forbidden-delete"),
		commentapp.DeleteCommentCommand{
			PostID: "post-err-sem", CommentID: created.ID, ActorID: "persona-intruder",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_forbidden_delete")
}

func TestPinCommentByNonPostAuthorEmitsCommentPinForbidden(t *testing.T) {
	service, _ := newCommentErrorSemanticsService()
	created := createErrSemComment(t, service, "err-sem-pin-forbidden-create", commentapp.CreateCommentCommand{
		PostID: "post-err-sem", ActorID: "persona-author", Content: "等待置顶的评论",
	})
	_, err := service.PinComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-pin-forbidden"),
		commentapp.ChangeCommentPinCommand{
			PostID: "post-err-sem", CommentID: created.ID, ActorID: "persona-intruder",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_pin_forbidden")
}

func TestPinReplyEmitsCommentPinInvalidTarget(t *testing.T) {
	service, _ := newCommentErrorSemanticsService()
	parent := createErrSemComment(t, service, "err-sem-pin-parent", commentapp.CreateCommentCommand{
		PostID: "post-err-sem", ActorID: "persona-author", Content: "一级评论",
	})
	reply := createErrSemComment(t, service, "err-sem-pin-reply", commentapp.CreateCommentCommand{
		PostID: "post-err-sem", ActorID: "persona-replier",
		Content: "二级回复", ReplyToCommentID: parent.ID,
	})
	_, err := service.PinComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-pin-invalid-target"),
		commentapp.ChangeCommentPinCommand{
			PostID: "post-err-sem", CommentID: reply.ID, ActorID: "persona-post-owner",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_pin_invalid_target")
}

// invalidReplyTargetRelations 返回缺失作者身份的 reply target，驱动
// domain 层 ErrInvalidReplyTarget 经 mapDomainError 映射到对象专属错误码。
type invalidReplyTargetRelations struct{}

func (invalidReplyTargetRelations) FindReplyTarget(
	_ context.Context,
	commentID string,
) (commentmodel.ReplyTarget, bool, error) {
	return commentmodel.ReplyTarget{
		ID:     commentID,
		PostID: "post-err-sem",
		Status: commentmodel.StatusActive,
	}, true, nil
}

func TestCreateCommentWithCorruptReplyTargetEmitsCommentParentInvalid(t *testing.T) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-err-sem", "persona-post-owner")
	ports := commentapp.BindDataPorts(
		store,
		store,
		posttestsupport.NewReactionStore(),
		store,
		store,
	)
	ports.Relations = invalidReplyTargetRelations{}
	service := commentapp.NewCommentService(ports)
	_, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-parent-invalid"),
		commentapp.CreateCommentCommand{
			PostID: "post-err-sem", ActorID: "persona-replier",
			Content: "回复目标已损坏", ReplyToCommentID: "comment-corrupt-target",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_parent_invalid")
}

func TestCreateCommentWithTooManyAttachmentsEmitsCommentAttachmentLimitExceeded(t *testing.T) {
	service, _ := newCommentErrorSemanticsService()
	overLimit := make([]string, 0, commentmodel.MaxAttachmentMediaIDs+1)
	for i := 0; i <= commentmodel.MaxAttachmentMediaIDs; i++ {
		overLimit = append(overLimit, "media-"+string(rune('a'+i)))
	}
	_, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-attachment-limit"),
		commentapp.CreateCommentCommand{
			PostID: "post-err-sem", ActorID: "persona-author",
			Content: "附件超限", AttachmentMediaIDs: overLimit,
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_attachment_limit_exceeded")
}

func TestHideCommentWithoutOperatorEmitsCommentModerationForbidden(t *testing.T) {
	service, _ := newCommentErrorSemanticsService()
	created := createErrSemComment(t, service, "err-sem-moderation-create", commentapp.CreateCommentCommand{
		PostID: "post-err-sem", ActorID: "persona-author", Content: "等待治理的评论",
	})
	_, err := service.HideComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-moderation-forbidden"),
		commentapp.HideCommentCommand{
			CommentID: created.ID, OperatorID: "", Reason: "no operator",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_moderation_forbidden")
}

func TestRestoreActiveCommentEmitsCommentStatusTransitionInvalid(t *testing.T) {
	service, _ := newCommentErrorSemanticsService()
	created := createErrSemComment(t, service, "err-sem-transition-create", commentapp.CreateCommentCommand{
		PostID: "post-err-sem", ActorID: "persona-author", Content: "从未隐藏的评论",
	})
	_, err := service.RestoreComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-transition-invalid"),
		commentapp.RestoreCommentCommand{
			CommentID: created.ID, OperatorID: "operator-moderation", Reason: "restore active",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.comment_status_transition_invalid")
}

// commitFailingStore 包装对象 testsupport Store，仅覆盖 Commit 以驱动
// application 层共享错误码（version_conflict / storage_write_failed）的
// 真实 emit 点；其余端口继续走真实实现。
type commitFailingStore struct {
	*commenttestsupport.Store
	commitErr error
}

func (s *commitFailingStore) Commit(
	context.Context,
	commentports.Commit,
) (commentports.CommitResult, error) {
	return commentports.CommitResult{}, s.commitErr
}

func newCommitFailingCommentService(commitErr error) (*commentapp.CommentService, *commenttestsupport.Store) {
	inner := commenttestsupport.NewStore()
	inner.SeedPost("post-err-sem", "persona-post-owner")
	wrapper := &commitFailingStore{Store: inner, commitErr: commitErr}
	return commentapp.NewCommentService(commentapp.BindDataPorts(
		wrapper,
		inner,
		posttestsupport.NewReactionStore(),
		inner,
		inner,
	)), inner
}

func TestDeleteCommentExhaustedRetriesEmitVersionConflict(t *testing.T) {
	// 先用正常 store 提交一条评论，再让后续 Commit 恒返回版本冲突，
	// 驱动 DeleteComment 的三次 CAS 重试收敛到共享 version_conflict。
	seeded, seedStore := newCommentErrorSemanticsService()
	created := createErrSemComment(t, seeded, "err-sem-version-create", commentapp.CreateCommentCommand{
		PostID: "post-err-sem", ActorID: "persona-author", Content: "并发修改的评论",
	})
	conflicting := commentapp.NewCommentService(commentapp.BindDataPorts(
		&commitFailingStore{
			Store: seedStore,
			commitErr: contentgenerated.AppErrorFromVersionConflict(
				"simulated concurrent comment mutation",
			),
		},
		seedStore,
		posttestsupport.NewReactionStore(),
		seedStore,
		seedStore,
	))
	_, err := conflicting.DeleteComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-version-conflict"),
		commentapp.DeleteCommentCommand{
			PostID: "post-err-sem", CommentID: created.ID, ActorID: "persona-author",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.USER.version_conflict")
}

func TestCreateCommentCommitFailureEmitsStorageWriteFailed(t *testing.T) {
	service, _ := newCommitFailingCommentService(errors.New("comment store connection reset"))
	_, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-storage-write"),
		commentapp.CreateCommentCommand{
			PostID: "post-err-sem", ActorID: "persona-author", Content: "提交失败的评论",
		},
	)
	requireCommentAppErrorCode(t, err, "CONTENT.SYSTEM.storage_write_failed")
}
