// Package ports 定义 Comment 专属的持久化与关系契约。
package ports

import (
	"context"
	"time"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

// OutboxEvent 是 Comment 对象边界持久化的不可变事实。普通命令使用
// Comment identity/version；Post 删除驱动的 CommentsTombstoned 批量事实使用
// 源 PostDeleted identity/version，避免伪造不存在的 Comment 聚合版本。
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	Checkpoint       string
}

type TombstoneCommentsByPostCommand struct {
	PostID            string
	SourceEventID     string
	SourcePostVersion int64
	OccurredAt        time.Time
}

type Commit struct {
	Aggregate        *commentmodel.Comment
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	AuthorRateLimit  *AuthorRateLimit
	Events           []OutboxEvent
}

// AuthorRateLimit 是 CreateComment 随聚合提交执行的权威滑动窗口约束。
// Store 必须在同一事务内先按 AuthorID 串行化，再校验现有 Comment 数并写入新聚合。
type AuthorRateLimit struct {
	AuthorID    string
	EvaluatedAt time.Time
	Windows     []AuthorRateWindow
}

type AuthorRateWindow struct {
	Since time.Time
	Max   int64
}

type CommitResult struct {
	Aggregate *commentmodel.Comment
	Replayed  bool
}

type IdempotentReceipt struct {
	Aggregate        *commentmodel.Comment
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

// AggregateStore 只负责 Comment 状态、命令回执、CAS 与事务 outbox；
// 它不持有 Post 状态或 Post.commentCount。
type AggregateStore interface {
	Load(ctx context.Context, commentID string) (*commentmodel.Comment, bool, error)
	FindReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (CommitResult, bool, error)
	RecordIdempotentReceipt(ctx context.Context, receipt IdempotentReceipt) (CommitResult, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

// OutboxReader 供异步 Post.commentCount 投影及其他消费者重放 Comment 事实，
// 无须查询聚合集合。
type OutboxReader interface {
	ReadAfter(ctx context.Context, checkpoint string, limit int) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error
}

type OutboxPublisher interface {
	Publish(ctx context.Context, event OutboxEvent) error
}
