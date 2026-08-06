// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-015
// readiness_case: consume-comment-lifecycle-local
package comment_test

import (
	"context"
	"testing"

	"quwoquan_service/runtime/commandmeta"
	contentgenerated "quwoquan_service/services/content-service/generated/content/comment"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

func TestCommentHotScoreProjectionHandlerRecomputesParentAfterReplyModeration(t *testing.T) {
	t.Parallel()

	projection := &hotScoreProjectionFixture{
		replyCount:   2,
		likeCount:    3,
		dislikeCount: 1,
	}
	handler := commentapp.NewCommentHotScoreProjectionHandler(
		projection,
		projection,
		projection,
	)

	err := handler.Apply(context.Background(), commentapp.CommentHotScoreProjection{
		CommentID: "parent-1",
	})
	if err != nil {
		t.Fatalf("投影回复治理事实失败：%v", err)
	}
	if projection.writtenCommentID != "parent-1" {
		t.Fatalf("重算目标 = %q，期望 parent-1", projection.writtenCommentID)
	}
	// (3 - 1) + 2 * 2 = 6。
	if projection.writtenScore != 6 {
		t.Fatalf("重算 hotScore = %d，期望 6", projection.writtenScore)
	}
}

func TestCommentReportResolutionHandlerHidesVerifiedComment(t *testing.T) {
	t.Parallel()

	commands := &commentModerationCommandsFixture{}
	handler := commentapp.NewCommentReportResolutionHandler(commands)
	if err := handler.HideComment(context.Background(), commentapp.ResolvedCommentReport{
		ReportID:   "report-1",
		CommentID:  "comment-1",
		ReviewerID: "operator-1",
	}); err != nil {
		t.Fatalf("apply resolved Comment report: %v", err)
	}
	if commands.calls != 1 || commands.command.CommentID != "comment-1" ||
		commands.command.OperatorID != "operator-1" ||
		commands.command.Reason != "resolved_report:report-1" {
		t.Fatalf("HideComment command drifted: calls=%d command=%+v", commands.calls, commands.command)
	}
	if commands.idempotencyKey != "report-comment-moderation:report-1" {
		t.Fatalf("idempotency key=%q", commands.idempotencyKey)
	}
}

func TestCommentReportResolutionPublisherFiltersNonRemovalAndAcknowledgesConvergedState(t *testing.T) {
	t.Parallel()

	commands := &commentModerationCommandsFixture{}
	publisher := commentapp.NewReportResolutionPublisher(
		commentapp.NewCommentReportResolutionHandler(commands),
	)
	if err := publisher.Publish(context.Background(), reportports.OutboxEvent{
		EventID:   "report-event-warn",
		EventType: "content.report.ReportResolved",
		Payload:   []byte(`{"reportId":"report-warn","targetType":"comment","targetId":"comment-1","reviewerId":"operator-1","resolution":"warn"}`),
	}); err != nil {
		t.Fatalf("ignore non-removal resolution: %v", err)
	}
	if commands.calls != 0 {
		t.Fatalf("non-removal resolution called HideComment %d times", commands.calls)
	}

	commands.err = contentgenerated.AppErrorFromCommentStatusTransitionInvalid(
		"comment is already non-active",
	)
	if err := publisher.Publish(context.Background(), reportports.OutboxEvent{
		EventID:   "report-event-replayed",
		EventType: "content.report.ReportResolved",
		Payload:   []byte(`{"reportId":"report-replayed","targetType":"comment","targetId":"comment-1","reviewerId":"operator-1","resolution":"delete_content"}`),
	}); err != nil {
		t.Fatalf("converged Comment removal must acknowledge replay: %v", err)
	}
}

type hotScoreProjectionFixture struct {
	replyCount       int64
	likeCount        int64
	dislikeCount     int64
	writtenCommentID string
	writtenScore     int64
}

func (f *hotScoreProjectionFixture) ReadReplySummaries(
	_ context.Context,
	parentCommentIDs []string,
	_ int,
	_ []string,
) (map[string]commentmodel.ReplySummary, error) {
	result := make(map[string]commentmodel.ReplySummary, len(parentCommentIDs))
	for _, commentID := range parentCommentIDs {
		result[commentID] = commentmodel.ReplySummary{Count: f.replyCount}
	}
	return result, nil
}

func (f *hotScoreProjectionFixture) ReadCommentReactionCounts(
	_ context.Context,
	commentIDs []string,
) (map[string]reactiondomain.CommentReactionCounts, error) {
	result := make(
		map[string]reactiondomain.CommentReactionCounts,
		len(commentIDs),
	)
	for _, commentID := range commentIDs {
		result[commentID] = reactiondomain.CommentReactionCounts{
			LikeCount:    f.likeCount,
			DislikeCount: f.dislikeCount,
		}
	}
	return result, nil
}

func (f *hotScoreProjectionFixture) ReadCommentReactionValues(
	_ context.Context,
	_ reactiondomain.Actor,
	_ []string,
) (map[string]reactiondomain.Value, error) {
	return map[string]reactiondomain.Value{}, nil
}

func (f *hotScoreProjectionFixture) ReadAuthorLikedFlags(
	_ context.Context,
	_ map[string][]string,
) (map[string]bool, error) {
	return map[string]bool{}, nil
}

func (f *hotScoreProjectionFixture) SetCommentHotScore(
	_ context.Context,
	commentID string,
	score int64,
) (bool, error) {
	f.writtenCommentID = commentID
	f.writtenScore = score
	return true, nil
}

type commentModerationCommandsFixture struct {
	calls          int
	command        commentapp.HideCommentCommand
	idempotencyKey string
	err            error
}

func (f *commentModerationCommandsFixture) HideComment(
	ctx context.Context,
	command commentapp.HideCommentCommand,
) (commentapp.CommentCommandResult, error) {
	f.calls++
	f.command = command
	f.idempotencyKey = commandmeta.IdempotencyKey(ctx)
	return commentapp.CommentCommandResult{}, f.err
}
