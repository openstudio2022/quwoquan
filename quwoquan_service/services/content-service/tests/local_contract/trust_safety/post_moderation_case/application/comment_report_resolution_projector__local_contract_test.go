package moderation_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	"testing"

	contentgenerated "quwoquan_service/services/content-service/generated/content/comment"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

func TestCommentReportResolutionProjectorHidesVerifiedComment(t *testing.T) {
	t.Parallel()

	commands := &commentModerationCommandsFixture{}
	projector := NewCommentReportResolutionProjector(commands)
	err := projector.Publish(context.Background(), reportports.OutboxEvent{
		EventID:   "report-event-1",
		EventType: "content.report.resolved",
		Payload: []byte(
			`{"reportId":"report-1","targetType":"comment","targetId":"comment-1","reviewerId":"operator-1","resolution":"delete_content"}`,
		),
	})
	if err != nil {
		t.Fatalf("投影已核实评论举报失败：%v", err)
	}
	if commands.calls != 1 {
		t.Fatalf("HideComment 调用次数 = %d，期望 1", commands.calls)
	}
	if commands.command.CommentID != "comment-1" ||
		commands.command.OperatorID != "operator-1" ||
		commands.command.Reason != "resolved_report:report-1" {
		t.Fatalf("HideComment 命令不正确：%+v", commands.command)
	}
	if commands.idempotencyKey != "report-comment-moderation:report-1" {
		t.Fatalf("幂等键 = %q", commands.idempotencyKey)
	}
}

func TestCommentReportResolutionProjectorIgnoresNonRemovalResolution(t *testing.T) {
	t.Parallel()

	commands := &commentModerationCommandsFixture{}
	projector := NewCommentReportResolutionProjector(commands)
	err := projector.Publish(context.Background(), reportports.OutboxEvent{
		EventID:   "report-event-warn",
		EventType: "content.report.resolved",
		Payload: []byte(
			`{"reportId":"report-warn","targetType":"comment","targetId":"comment-1","reviewerId":"operator-1","resolution":"warn"}`,
		),
	})
	if err != nil {
		t.Fatalf("忽略 warn 结果失败：%v", err)
	}
	if commands.calls != 0 {
		t.Fatalf("warn 结果不应隐藏评论，调用次数 = %d", commands.calls)
	}
}

func TestCommentReportResolutionProjectorAcceptsAlreadyRemovedTarget(t *testing.T) {
	t.Parallel()

	commands := &commentModerationCommandsFixture{
		err: contentgenerated.AppErrorFromCommentStatusTransitionInvalid(
			"comment is already non-active",
		),
	}
	projector := NewCommentReportResolutionProjector(commands)
	err := projector.Publish(context.Background(), reportports.OutboxEvent{
		EventID:   "report-event-replayed",
		EventType: "content.report.resolved",
		Payload: []byte(
			`{"reportId":"report-replayed","targetType":"comment","targetId":"comment-1","reviewerId":"operator-1","resolution":"delete_content"}`,
		),
	})
	if err != nil {
		t.Fatalf("已不可见目标应视为治理意图满足：%v", err)
	}
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
