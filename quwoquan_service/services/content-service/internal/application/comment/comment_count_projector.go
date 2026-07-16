package comment

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
)

type CommentCountProjectionWriter interface {
	SetCommentCount(ctx context.Context, postID string, count int64) (bool, error)
}

type CommentCountProjector struct {
	counts commentports.CountReader
	writer CommentCountProjectionWriter
}

func NewCommentCountProjector(
	counts commentports.CountReader,
	writer CommentCountProjectionWriter,
) *CommentCountProjector {
	return &CommentCountProjector{counts: counts, writer: writer}
}

func (p *CommentCountProjector) Publish(ctx context.Context, event commentports.OutboxEvent) error {
	if p == nil || p.counts == nil || p.writer == nil {
		return fmt.Errorf("Comment count projector is not configured")
	}
	if event.EventType != commentCreatedEventType && event.EventType != commentDeletedEventType {
		return nil
	}
	var payload struct {
		PostID string `json:"postId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode Comment count event: %w", err)
	}
	postID := strings.TrimSpace(payload.PostID)
	if postID == "" {
		return fmt.Errorf("Comment count event has no postId")
	}
	count, err := p.counts.CountByPost(ctx, postID)
	if err != nil {
		return fmt.Errorf("count Comment projection: %w", err)
	}
	updated, err := p.writer.SetCommentCount(ctx, postID, count)
	if err != nil {
		return fmt.Errorf("write Post comment count projection: %w", err)
	}
	if !updated {
		return fmt.Errorf("Post comment count target %q is missing", postID)
	}
	return nil
}

var _ commentports.OutboxPublisher = (*CommentCountProjector)(nil)
