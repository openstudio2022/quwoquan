package ports

import (
	"context"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

// OutboxEvent is an immutable media-domain fact persisted in the same Mongo
// transaction as the aggregate version and idempotency receipt.
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateType    string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	Checkpoint       string
}

type MediaAssetCommit struct {
	Aggregate        *mediamodel.MediaAsset
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
	Discard          bool
}

type MediaAssetCommitResult struct {
	Aggregate *mediamodel.MediaAsset
	Replayed  bool
}

// MediaAssetNoopReceipt 是目标状态已满足的命名 set（如 access policy 已一致）
// 的持久化回执：不递增 aggregate version、不产生 outbox 事实，但相同 key 的
// 后续重试只重放本次结果。
type MediaAssetNoopReceipt struct {
	Aggregate        *mediamodel.MediaAsset
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

// MediaAssetStore is the object-specific write port for durable assets.
type MediaAssetStore interface {
	LoadMediaAsset(
		ctx context.Context,
		assetID string,
	) (*mediamodel.MediaAsset, bool, error)
	FindMediaAssetReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (MediaAssetCommitResult, bool, error)
	RecordMediaAssetNoopReceipt(
		ctx context.Context,
		receipt MediaAssetNoopReceipt,
	) (MediaAssetCommitResult, error)
	CommitMediaAsset(
		ctx context.Context,
		commit MediaAssetCommit,
	) (MediaAssetCommitResult, error)
}

// OutboxReader exists for relay workers. It is intentionally independent from
// Post outbox interfaces so media replays cannot be mixed with Post facts.
type OutboxReader interface {
	ReadMediaOutboxAfter(
		ctx context.Context,
		checkpoint string,
		limit int,
	) ([]OutboxEvent, error)
}

// MediaAssetOutboxReader isolates the MediaAsset publication stream from the
// sibling MediaUploadSession outbox that shares the same Mongo store.
type MediaAssetOutboxReader interface {
	ReadMediaAssetOutboxAfter(
		ctx context.Context,
		checkpoint string,
		limit int,
	) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error
}

type OutboxPublisher interface {
	Publish(ctx context.Context, event OutboxEvent) error
}
