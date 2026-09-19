// Package ports 定义 ContentReaction 命令侧唯一的对象专属持久化端口。
package ports

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"strings"
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
const ContentReactionOutboxPartitionCount = 32

var ErrOutboxLeaseLost = errors.New("ContentReaction outbox partition lease lost")

// OutboxFact separates stable aggregate/event identity from transport order.
// PartitionSequence is contiguous only within PartitionID.
type OutboxFact struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	// Checkpoint is retained only as a source-compatible diagnostic field for
	// lifecycle tests; relay progress is exclusively partitionSequence + fenced checkpoint.
	Checkpoint        string
	PartitionKey      string
	PartitionID       int
	PartitionSequence int64
}

type OutboxPartitionLease struct {
	Consumer    string
	Owner       string
	PartitionID int
	Sequence    int64
	LeaseEpoch  int64
	LeaseUntil  time.Time
}

func OutboxPartitionForKey(key string) int {
	digest := sha256.Sum256([]byte(strings.TrimSpace(key)))
	return int(binary.BigEndian.Uint32(digest[:4]) % ContentReactionOutboxPartitionCount)
}

// Commit 保留一次命令提交的并发、幂等和事实边界。
// Changed=false 允许为已存在状态持久化 receipt，而不虚增 aggregate version 或事件。
type Commit struct {
	Aggregate        *reaction.ContentReaction
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	BasisDigest      string
	AcceptUntil      time.Time
	ReceiptExpiresAt time.Time
	Changed          bool
	Events           []OutboxFact
}

type ReceiptOutcome string

const (
	ReceiptOutcomeCommitted          ReceiptOutcome = "committed"
	ReceiptOutcomeRejected           ReceiptOutcome = "rejected"
	ReceiptOutcomeExpired            ReceiptOutcome = "expired"
	ReceiptOutcomeHistoryUnavailable ReceiptOutcome = "history_unavailable"
)

type CommitResult struct {
	Aggregate *reaction.ContentReaction
	Changed   bool
	Replayed  bool
	Outcome   ReceiptOutcome
}

type AggregateStore interface {
	Load(ctx context.Context, aggregateID string) (*reaction.ContentReaction, bool, error)
	FindReceipt(ctx context.Context, identity reaction.Identity, idempotencyKey, commandName, commandDigest, basisDigest string) (CommitResult, bool, error)
	RecoverReceipt(ctx context.Context, actor reaction.Actor, idempotencyKey, commandName string) (CommitResult, bool, error)
	FinalizeExpired(ctx context.Context, identity reaction.Identity, idempotencyKey, commandName, commandDigest, basisDigest string, acceptUntil time.Time) (CommitResult, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

// OutboxReader leases and reads fixed partitions. A gap is an error; callers
// must not jump to a later sequence.
type OutboxReader interface {
	ClaimOutboxPartitions(ctx context.Context, consumer, owner string, lease time.Duration, maxPartitions int) ([]OutboxPartitionLease, error)
	ReadOutboxPartition(ctx context.Context, lease OutboxPartitionLease, limit int) ([]OutboxFact, error)
}

// ProjectionCheckpointStore fences the exact next checkpoint with leaseEpoch.
type ProjectionCheckpointStore interface {
	AdvanceOutboxCheckpoint(ctx context.Context, lease OutboxPartitionLease, fact OutboxFact) error
}

// OutboxPublisher 是 relay 在 aggregate transaction 提交后的唯一投递边界。
type OutboxPublisher interface {
	Publish(ctx context.Context, fact OutboxFact) error
}
