// Package ports 定义 HomepageClaimRequest 专属持久化契约。
package ports

import (
	"context"
	"time"

	claimmodel "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model"
)

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
}

type Commit struct {
	Aggregate        *claimmodel.HomepageClaimRequest
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
}

type CommitResult struct {
	Aggregate *claimmodel.HomepageClaimRequest
	Replayed  bool
}

type NoopReceipt struct {
	Aggregate        *claimmodel.HomepageClaimRequest
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

// AggregateStore 只负责聚合状态与 CAS，不承载 Homepage 投影写入。
type AggregateStore interface {
	Load(ctx context.Context, claimRequestID string) (*claimmodel.HomepageClaimRequest, bool, error)
	FindPending(
		ctx context.Context,
		homepageID string,
		requesterPersonaID string,
	) (*claimmodel.HomepageClaimRequest, bool, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

type QueueQuery struct {
	HomepageID string
	Status     claimmodel.Status
	Cursor     string
	Limit      int
}

type QueuePage struct {
	Items      []claimmodel.Snapshot
	NextCursor string
}

// QueueReader 是 Ops 治理队列的对象专属具名读端口。
type QueueReader interface {
	ListQueue(ctx context.Context, query QueueQuery) (QueuePage, error)
}

type ReceiptStore interface {
	FindReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (CommitResult, bool, error)
	RecordNoopReceipt(ctx context.Context, receipt NoopReceipt) (CommitResult, error)
}

type OutboxReader interface {
	ReadAfter(ctx context.Context, checkpoint string, limit int) ([]OutboxEvent, error)
}

type OutboxPublisher interface {
	Publish(ctx context.Context, event OutboxEvent) error
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error
}
