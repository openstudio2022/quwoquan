package reaction

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

type commentDeletedLifecycleFact struct {
	CommentID       string    `json:"commentId"`
	Version         int64     `json:"version"`
	PostID          string    `json:"postId"`
	AuthorID        string    `json:"authorId"`
	ParentCommentID string    `json:"parentCommentId,omitempty"`
	DeletedAt       time.Time `json:"deletedAt"`
}

type CommentDeletionConsumer struct{ cleanup LifecycleCleanupPort }

func NewCommentDeletionConsumer(cleanup LifecycleCleanupPort) *CommentDeletionConsumer {
	return &CommentDeletionConsumer{cleanup: cleanup}
}

func (consumer *CommentDeletionConsumer) Publish(ctx context.Context, event commentports.OutboxEvent) error {
	if event.EventType != "CommentDeleted" {
		return nil
	}
	if consumer == nil || consumer.cleanup == nil {
		return fmt.Errorf("Comment deletion ContentReaction cleanup is not configured")
	}
	payload, err := decodeCommentDeletedLifecycleFact(event)
	if err != nil {
		return err
	}
	target, err := reactiondomain.NewTarget(reactiondomain.TargetKindComment, payload.CommentID)
	if err != nil {
		return err
	}
	return consumer.cleanup.CleanupTarget(ctx, target, LifecycleCleanupAuthorization{
		Source: "CommentDeleted", SourceEventID: event.EventID, SourceVersion: event.AggregateVersion,
		Tombstone: fmt.Sprintf("comment:%s:v%d", payload.CommentID, payload.Version), OccurredAt: event.OccurredAt,
	})
}

func decodeCommentDeletedLifecycleFact(event commentports.OutboxEvent) (commentDeletedLifecycleFact, error) {
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return commentDeletedLifecycleFact{}, fmt.Errorf("CommentDeleted lifecycle identity is incomplete")
	}
	var payload commentDeletedLifecycleFact
	decoder := json.NewDecoder(bytes.NewReader(event.Payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return payload, fmt.Errorf("decode CommentDeleted lifecycle fact: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return payload, fmt.Errorf("CommentDeleted lifecycle fact contains trailing JSON")
	}
	if payload.CommentID != event.AggregateID || payload.Version != event.AggregateVersion || strings.TrimSpace(payload.PostID) == "" || strings.TrimSpace(payload.AuthorID) == "" || payload.DeletedAt.IsZero() {
		return payload, fmt.Errorf("CommentDeleted lifecycle fact is invalid")
	}
	return payload, nil
}

var _ commentports.OutboxPublisher = (*CommentDeletionConsumer)(nil)
