package moderation

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"quwoquan_service/runtime/commandmeta"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

// ReportModerationHandler 消费 Report outbox 事实并为被举报的 Post 打开审核 Case。
// 它实现 reportports.OutboxPublisher，作为 report relay 的第二个具名 consumer
// （checkpoint 独立于 runtime events fan-out）。
//
// 幂等语义：Case 按 reportId 派生稳定 Idempotency-Key 重放；同一 post revision
// 的多条举报由 OpenPostModerationCase 的 revision 唯一约束幂等归并到既有 Case。
type ReportModerationHandler struct {
	commands PostModerationCaseCommandFacet
	posts    postports.PostRevisionSliceReader
}

func NewReportModerationHandler(
	commands PostModerationCaseCommandFacet,
	posts postports.PostRevisionSliceReader,
) *ReportModerationHandler {
	if commands == nil || posts == nil {
		panic("ReportModerationHandler requires moderation command facet and post revision reader")
	}
	return &ReportModerationHandler{commands: commands, posts: posts}
}

type reportCreatedFact struct {
	ReportID   string `json:"reportId"`
	TargetType string `json:"targetType"`
	TargetID   string `json:"targetId"`
}

// OpenPostModerationCase is the canonical lifecycle method for one committed
// post-targeted ReportCreated fact.
func (h *ReportModerationHandler) OpenPostModerationCase(
	ctx context.Context,
	event reportports.OutboxEvent,
) error {
	if h == nil || h.commands == nil || h.posts == nil {
		return fmt.Errorf("report moderation handler is not configured")
	}
	if event.EventType != "content.report.ReportCreated" {
		return nil
	}
	var fact reportCreatedFact
	if err := json.Unmarshal(event.Payload, &fact); err != nil {
		return fmt.Errorf("decode report created fact %q: %w", event.EventID, err)
	}
	if fact.TargetType != "post" {
		return nil
	}
	reportID := strings.TrimSpace(fact.ReportID)
	postID := strings.TrimSpace(fact.TargetID)
	if reportID == "" || postID == "" {
		return fmt.Errorf("report created fact %q is missing reportId or targetId", event.EventID)
	}
	revision, found, err := h.posts.FindPostRevision(ctx, postports.NewPostID(postID))
	if err != nil {
		return fmt.Errorf("read post revision for report %q: %w", reportID, err)
	}
	if !found {
		// 目标内容已删除或不可读：无 revision 可审，事实照常推进 checkpoint。
		return nil
	}
	ctx = commandmeta.WithIdempotencyKey(ctx, "report-moderation:"+reportID)
	if _, err := h.commands.OpenPostModerationCase(ctx, OpenPostModerationCaseCommand{
		PostID:        string(revision.PostID),
		PostVersion:   revision.Version,
		ContentDigest: revision.ContentDigest,
	}); err != nil {
		return fmt.Errorf("open moderation case for report %q: %w", reportID, err)
	}
	return nil
}

func (h *ReportModerationHandler) Publish(
	ctx context.Context,
	event reportports.OutboxEvent,
) error {
	return h.OpenPostModerationCase(ctx, event)
}

var _ reportports.OutboxPublisher = (*ReportModerationHandler)(nil)
