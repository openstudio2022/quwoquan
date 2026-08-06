package post

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
)

const (
	commentCreatedProjectionEventType     = "CommentCreated"
	commentDeletedProjectionEventType     = "CommentDeleted"
	commentModeratedProjectionEventType   = "CommentModerated"
	commentsTombstonedProjectionEventType = "CommentsTombstoned"
)

// CommentCountReader exposes only the authoritative active Comment count that
// the Post projection needs; no Comment persistence implementation leaks in.
type CommentCountReader interface {
	CountByPost(ctx context.Context, postID string) (int64, error)
}

type CommentCountProjectionWriter interface {
	SetCommentCount(ctx context.Context, postID string, count int64) (bool, error)
}

type CommentCountProjection struct {
	PostID string
}

// CommentCountProjectionHandler owns the Comment lifecycle -> Post count
// projection declared by content.post.
type CommentCountProjectionHandler struct {
	counts CommentCountReader
	writer CommentCountProjectionWriter
}

func NewCommentCountProjectionHandler(
	counts CommentCountReader,
	writer CommentCountProjectionWriter,
) *CommentCountProjectionHandler {
	if counts == nil || writer == nil {
		panic("CommentCountProjectionHandler requires count reader and projection writer")
	}
	return &CommentCountProjectionHandler{counts: counts, writer: writer}
}

// Apply converges Post.commentCount from the authoritative Comment store. It
// deliberately avoids increments so outbox replay is idempotent.
func (h *CommentCountProjectionHandler) Apply(
	ctx context.Context,
	projection CommentCountProjection,
) error {
	if h == nil || h.counts == nil || h.writer == nil {
		return fmt.Errorf("Comment count projection handler is not configured")
	}
	postID := strings.TrimSpace(projection.PostID)
	if postID == "" {
		return fmt.Errorf("Comment count projection has no postId")
	}
	count, err := h.counts.CountByPost(ctx, postID)
	if err != nil {
		return fmt.Errorf("count Comment projection: %w", err)
	}
	updated, err := h.writer.SetCommentCount(ctx, postID, count)
	if err != nil {
		return fmt.Errorf("write Post comment count projection: %w", err)
	}
	if !updated {
		return fmt.Errorf("Post comment count target %q is missing", postID)
	}
	return nil
}

// CommentCountProjectionPublisher adapts Comment outbox facts to the owning
// Post lifecycle handler.
type CommentCountProjectionPublisher struct {
	handler *CommentCountProjectionHandler
}

func NewCommentCountProjectionPublisher(
	handler *CommentCountProjectionHandler,
) *CommentCountProjectionPublisher {
	if handler == nil {
		panic("CommentCountProjectionPublisher requires handler")
	}
	return &CommentCountProjectionPublisher{handler: handler}
}

func (p *CommentCountProjectionPublisher) Publish(
	ctx context.Context,
	event commentports.OutboxEvent,
) error {
	if p == nil || p.handler == nil {
		return fmt.Errorf("Comment count projection publisher is not configured")
	}
	if event.EventType != commentCreatedProjectionEventType &&
		event.EventType != commentDeletedProjectionEventType &&
		event.EventType != commentModeratedProjectionEventType &&
		event.EventType != commentsTombstonedProjectionEventType {
		return nil
	}
	var payload struct {
		PostID string `json:"postId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode Comment count event: %w", err)
	}
	return p.handler.Apply(ctx, CommentCountProjection{PostID: payload.PostID})
}

var _ commentports.OutboxPublisher = (*CommentCountProjectionPublisher)(nil)
