package comment

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/comment"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const (
	reportResolvedEventType    = "content.report.ReportResolved"
	commentReportTargetType    = "comment"
	deleteContentResolution    = "delete_content"
	reportModerationKeyPrefix  = "report-comment-moderation:"
	reportModerationReasonType = "resolved_report"
)

// CommentModerationCommandFacet is the public Comment command boundary used by
// cross-object event adapters. It never exposes Comment persistence internals.
type CommentModerationCommandFacet interface {
	HideComment(
		context.Context,
		HideCommentCommand,
	) (CommentCommandResult, error)
}

// ResolvedCommentReport is the object-local command produced from one verified
// ReportResolved fact. The Report wire is decoded before this boundary.
type ResolvedCommentReport struct {
	ReportID   string
	CommentID  string
	ReviewerID string
}

// CommentReportResolutionHandler owns the ReportResolved -> Comment hidden
// lifecycle transition declared by content.comment.
type CommentReportResolutionHandler struct {
	comments CommentModerationCommandFacet
}

func NewCommentReportResolutionHandler(
	comments CommentModerationCommandFacet,
) *CommentReportResolutionHandler {
	if comments == nil {
		panic("CommentReportResolutionHandler requires Comment command facet")
	}
	return &CommentReportResolutionHandler{comments: comments}
}

// HideComment applies one verified report resolution through the canonical
// Comment command facet. Replays that already achieved a non-active state are
// acknowledged as converged.
func (h *CommentReportResolutionHandler) HideComment(
	ctx context.Context,
	resolution ResolvedCommentReport,
) error {
	if h == nil || h.comments == nil {
		return fmt.Errorf("Comment report resolution handler is not configured")
	}
	reportID := strings.TrimSpace(resolution.ReportID)
	commentID := strings.TrimSpace(resolution.CommentID)
	reviewerID := strings.TrimSpace(resolution.ReviewerID)
	if reportID == "" || commentID == "" || reviewerID == "" {
		return fmt.Errorf("resolved Comment report is missing reportId, commentId or reviewerId")
	}
	ctx = commandmeta.WithIdempotencyKey(ctx, reportModerationKeyPrefix+reportID)
	_, err := h.comments.HideComment(ctx, HideCommentCommand{
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

// ReportResolutionPublisher is the Report outbox adapter for the owning
// Comment handler. It rejects malformed removal facts before invoking behavior.
type ReportResolutionPublisher struct {
	handler *CommentReportResolutionHandler
}

func NewReportResolutionPublisher(
	handler *CommentReportResolutionHandler,
) *ReportResolutionPublisher {
	if handler == nil {
		panic("ReportResolutionPublisher requires Comment report resolution handler")
	}
	return &ReportResolutionPublisher{handler: handler}
}

func (p *ReportResolutionPublisher) Publish(
	ctx context.Context,
	event reportports.OutboxEvent,
) error {
	if p == nil || p.handler == nil {
		return fmt.Errorf("Comment report resolution publisher is not configured")
	}
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
	return p.handler.HideComment(ctx, ResolvedCommentReport{
		ReportID:   fact.ReportID,
		CommentID:  fact.TargetID,
		ReviewerID: fact.ReviewerID,
	})
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

var _ reportports.OutboxPublisher = (*ReportResolutionPublisher)(nil)
