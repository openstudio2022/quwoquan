package comment

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

const commentsTombstonedEventType = "CommentsTombstoned"

// CommentTombstoneWriter 把宿主 Post 删除的级联事实落到 comments 集合：
// active|hidden → tombstoned 批量迁移，并在同一事务写入 CommentsTombstoned outbox。
type CommentTombstoneWriter interface {
	TombstoneCommentsByPost(ctx context.Context, postID string) (int64, error)
}

// CommentTombstoneProjector 消费 PostDeleted 事实，驱动该 Post 全部评论级联 tombstone。
// 幂等：重放时 active|hidden 集合为空，UpdateMany 天然零改动。
type CommentTombstoneProjector struct {
	writer CommentTombstoneWriter
}

func NewCommentTombstoneProjector(writer CommentTombstoneWriter) *CommentTombstoneProjector {
	return &CommentTombstoneProjector{writer: writer}
}

func (p *CommentTombstoneProjector) Publish(ctx context.Context, event postports.OutboxEvent) error {
	if p == nil || p.writer == nil {
		return fmt.Errorf("Comment tombstone projector is not configured")
	}
	if event.EventType != "PostDeleted" {
		return nil
	}
	var payload struct {
		PostID string `json:"postId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode PostDeleted for comment tombstone: %w", err)
	}
	postID := strings.TrimSpace(payload.PostID)
	if postID == "" {
		return fmt.Errorf("PostDeleted event has no post id")
	}
	if _, err := p.writer.TombstoneCommentsByPost(ctx, postID); err != nil {
		return fmt.Errorf("tombstone comments for deleted post: %w", err)
	}
	return nil
}

var _ postports.OutboxPublisher = (*CommentTombstoneProjector)(nil)
