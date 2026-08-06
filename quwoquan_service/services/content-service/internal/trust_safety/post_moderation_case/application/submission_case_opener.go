package moderation

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"quwoquan_service/runtime/commandmeta"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const postSubmittedForReviewEventType = "PostSubmittedForReview"

// PostSubmissionModerationHandler 把不可公开的 pending_review Post 事实翻译为审核 Case 命令。
// Case 仍按 postId+version+digest 唯一，Post outbox 重放不会创建重复 Case。
type PostSubmissionModerationHandler struct {
	commands PostModerationCaseCommandFacet
}

func NewPostSubmissionModerationHandler(
	commands PostModerationCaseCommandFacet,
) *PostSubmissionModerationHandler {
	if commands == nil {
		panic("PostSubmissionModerationHandler requires moderation command facet")
	}
	return &PostSubmissionModerationHandler{commands: commands}
}

type postSubmittedForReviewFact struct {
	PostID           string `json:"postId"`
	Status           string `json:"status"`
	ModerationStatus string `json:"moderationStatus"`
	ContentDigest    string `json:"contentDigest"`
}

// OpenPostModerationCase is the canonical lifecycle method for a committed
// PostSubmittedForReview fact.
func (h *PostSubmissionModerationHandler) OpenPostModerationCase(
	ctx context.Context,
	event postports.OutboxEvent,
) error {
	if h == nil || h.commands == nil {
		return fmt.Errorf("post submission moderation handler is not configured")
	}
	if event.EventType != postSubmittedForReviewEventType {
		return nil
	}
	var fact postSubmittedForReviewFact
	if err := json.Unmarshal(event.Payload, &fact); err != nil {
		return fmt.Errorf(
			"decode PostSubmittedForReview %q: %w",
			event.EventID,
			err,
		)
	}
	postID := strings.TrimSpace(fact.PostID)
	digest := strings.TrimSpace(fact.ContentDigest)
	if postID == "" ||
		postID != strings.TrimSpace(event.AggregateID) ||
		event.AggregateVersion < 1 ||
		digest == "" ||
		fact.Status != "pending_review" ||
		fact.ModerationStatus != "pending" {
		return fmt.Errorf(
			"PostSubmittedForReview %q payload is inconsistent",
			event.EventID,
		)
	}
	ctx = commandmeta.WithIdempotencyKey(
		ctx,
		"post-submission-moderation:"+strings.TrimSpace(event.EventID),
	)
	_, err := h.commands.OpenPostModerationCase(
		ctx,
		OpenPostModerationCaseCommand{
			PostID:        postID,
			PostVersion:   event.AggregateVersion,
			ContentDigest: digest,
		},
	)
	if err != nil {
		return fmt.Errorf(
			"open moderation case for PostSubmittedForReview %q: %w",
			event.EventID,
			err,
		)
	}
	return nil
}

func (h *PostSubmissionModerationHandler) Publish(
	ctx context.Context,
	event postports.OutboxEvent,
) error {
	return h.OpenPostModerationCase(ctx, event)
}

var _ postports.OutboxPublisher = (*PostSubmissionModerationHandler)(nil)
