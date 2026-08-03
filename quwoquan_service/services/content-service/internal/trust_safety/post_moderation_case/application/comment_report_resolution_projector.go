package moderation

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/comment"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	"quwoquan_service/runtime/commandmeta"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const (
	reportResolvedEventType    = "content.report.resolved"
	commentReportTargetType    = "comment"
	deleteContentResolution    = "delete_content"
	reportModerationKeyPrefix  = "report-comment-moderation:"
	reportModerationReasonType = "resolved_report"
)

// CommentModerationCommandFacet 是 Report 投影写入 Comment 聚合的唯一公开命令面。
type CommentModerationCommandFacet interface {
	HideComment(
		context.Context,
		commentapp.HideCommentCommand,
	) (commentapp.CommentCommandResult, error)
}

// CommentReportResolutionProjector 把已核实的评论举报收敛为 Comment hidden 状态。
// Report 与 Comment 各自独立提交，通过 report outbox checkpoint 实现最终一致和重放安全。
type CommentReportResolutionProjector struct {
	comments CommentModerationCommandFacet
}

func NewCommentReportResolutionProjector(
	comments CommentModerationCommandFacet,
) *CommentReportResolutionProjector {
	if comments == nil {
		panic("CommentReportResolutionProjector requires Comment command facet")
	}
	return &CommentReportResolutionProjector{comments: comments}
}

func (p *CommentReportResolutionProjector) Publish(
	ctx context.Context,
	event reportports.OutboxEvent,
) error {
	if event.EventType != reportResolvedEventType {
		return nil
	}
	var fact struct {
		ReportID   string `json:"reportId"`
		TargetType string `json:"targetType"`
		TargetID   string `json:"targetId"`
		ReviewerID string `json:"reviewerId"`
		Resolution string `json:"resolution"`
	}
	if err := json.Unmarshal(event.Payload, &fact); err != nil {
		return fmt.Errorf("decode resolved Comment report fact %q: %w", event.EventID, err)
	}
	if strings.TrimSpace(fact.TargetType) != commentReportTargetType ||
		strings.TrimSpace(fact.Resolution) != deleteContentResolution {
		return nil
	}
	reportID := strings.TrimSpace(fact.ReportID)
	commentID := strings.TrimSpace(fact.TargetID)
	reviewerID := strings.TrimSpace(fact.ReviewerID)
	if reportID == "" || commentID == "" || reviewerID == "" {
		return fmt.Errorf(
			"resolved Comment report fact %q is missing reportId, targetId or reviewerId",
			event.EventID,
		)
	}
	ctx = commandmeta.WithIdempotencyKey(
		ctx,
		reportModerationKeyPrefix+reportID,
	)
	_, err := p.comments.HideComment(ctx, commentapp.HideCommentCommand{
		CommentID:  commentID,
		OperatorID: reviewerID,
		Reason:     reportModerationReasonType + ":" + reportID,
	})
	if commentRemovalAlreadySatisfied(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("hide Comment for resolved report %q: %w", reportID, err)
	}
	return nil
}

func commentRemovalAlreadySatisfied(err error) bool {
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		return false
	}
	code := appError.Code.String()
	return code == contentgenerated.ErrCommentNotFound.Error() ||
		code == contentgenerated.ErrCommentStatusTransitionInvalid.Error()
}

var _ reportports.OutboxPublisher = (*CommentReportResolutionProjector)(nil)
