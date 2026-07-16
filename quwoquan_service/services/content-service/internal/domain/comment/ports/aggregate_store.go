// Package ports 定义 Comment 专属的持久化与关系契约。
package ports

import (
	"context"
	"time"

	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
)

// OutboxEvent 是与 Comment 聚合版本在同一事务提交的不可变事实。
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	Checkpoint       string
}

type Commit struct {
	Aggregate        *commentmodel.Comment
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
}

type CommitResult struct {
	Aggregate *commentmodel.Comment
	Replayed  bool
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
