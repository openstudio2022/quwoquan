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

// SubmissionCaseOpener 把不可公开的 pending_review Post 事实翻译为审核 Case 命令。
// Case 仍按 postId+version+digest 唯一，Post outbox 重放不会创建重复 Case。
type SubmissionCaseOpener struct {
	commands PostModerationCaseCommandFacet
}

func NewSubmissionCaseOpener(
	commands PostModerationCaseCommandFacet,
) *SubmissionCaseOpener {
	if commands == nil {
		panic("SubmissionCaseOpener requires moderation command facet")
	}
	return &SubmissionCaseOpener{commands: commands}
}

type postSubmittedForReviewFact struct {
	PostID           string `json:"postId"`
	Status           string `json:"status"`
	ModerationStatus string `json:"moderationStatus"`
	ContentDigest    string `json:"contentDigest"`
}

func (o *SubmissionCaseOpener) Publish(
	ctx context.Context,
	event postports.OutboxEvent,
) error {
	if o == nil || o.commands == nil {
		return fmt.Errorf("submission case opener is not configured")
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
	_, err := o.commands.OpenPostModerationCase(
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

var _ postports.OutboxPublisher = (*SubmissionCaseOpener)(nil)
