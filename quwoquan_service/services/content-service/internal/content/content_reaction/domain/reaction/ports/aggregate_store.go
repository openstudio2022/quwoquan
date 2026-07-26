// Package ports 定义 ContentReaction 命令侧唯一的对象专属持久化端口。
package ports

import (
	"context"
	"time"

	reaction "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

// ProfileActivitySlice 是 ContentReaction 提供给 Profile interaction 的公开只读 Slice。
// 只允许 persona 维度 active reaction，不暴露聚合、receipt 或 device actor。
type ProfileActivitySlice struct {
	ReactionID string
	PostID     string
	ActorID    string
	OccurredAt time.Time
}

// ProfileActivityReader 是跨对象 Profile projection 的具名读端口。
// actorID 为空读取 received 候选，非空只读取该 persona 的 sent 候选。
type ProfileActivityReader interface {
	ListActiveProfileReactions(
		ctx context.Context,
		actorID string,
		limit int,
	) ([]ProfileActivitySlice, error)
}

type CommentReactionValueReader interface {
	ReadCommentReactionValues(
		ctx context.Context,
		actor reaction.Actor,
		commentIDs []string,
	) (map[string]reaction.Value, error)
}

// OutboxFact 必须与 ContentReaction 的同一版本原子提交。
type OutboxFact struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	// Checkpoint 仅由 OutboxReader 填充，consumer 必须原样持久化。
	Checkpoint string
}

// Commit 保留一次命令提交的并发、幂等和事实边界。
// Changed=false 允许为已存在状态持久化 receipt，而不虚增 aggregate version 或事件。
type Commit struct {
	Aggregate        *reaction.ContentReaction
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Changed          bool
	Events           []OutboxFact
}

type CommitResult struct {
	Aggregate *reaction.ContentReaction
	Changed   bool
	Replayed  bool
}

type AggregateStore interface {
	Load(ctx context.Context, aggregateID string) (*reaction.ContentReaction, bool, error)
	FindReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (CommitResult, bool, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

// OutboxReader 按全局单调 sequence 返回已经提交的 ContentReaction 事实。
type OutboxReader interface {
	ReadAfter(ctx context.Context, checkpoint string, limit int) ([]OutboxFact, error)
}

// ProjectionCheckpointStore 为每个 reaction consumer 保存独立重放水位。
type ProjectionCheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error
}

// OutboxPublisher 是 relay 在 aggregate transaction 提交后的唯一投递边界。
type OutboxPublisher interface {
	Publish(ctx context.Context, fact OutboxFact) error
}
