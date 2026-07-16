package ports

import (
	"context"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
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

type UploadSessionCommit struct {
	Aggregate        *mediamodel.MediaUploadSession
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
}

type MediaAssetCommit struct {
	Aggregate        *mediamodel.MediaAsset
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
}

// CompleteUploadCommit prevents a half-completed upload: session completion,
// asset creation, both idempotency receipts, and the two facts commit together.
type CompleteUploadCommit struct {
	Session          *mediamodel.MediaUploadSession
	ExpectedVersion  int64
	Asset            *mediamodel.MediaAsset
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
}

type UploadSessionCommitResult struct {
	Aggregate *mediamodel.MediaUploadSession
	Replayed  bool
}

type MediaAssetCommitResult struct {
	Aggregate *mediamodel.MediaAsset
	Replayed  bool
}

type CompleteUploadResult struct {
	Session  *mediamodel.MediaUploadSession
	Asset    *mediamodel.MediaAsset
	Replayed bool
}

// MediaUploadSessionStore is the object-specific write port for upload
// sessions. Production implementations must be durable Mongo stores.
type MediaUploadSessionStore interface {
	LoadUploadSession(
		ctx context.Context,
		sessionID string,
	) (*mediamodel.MediaUploadSession, bool, error)
	FindUploadSessionReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (UploadSessionCommitResult, bool, error)
	FindCompleteUploadReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (CompleteUploadResult, bool, error)
	CommitUploadSession(
		ctx context.Context,
		commit UploadSessionCommit,
	) (UploadSessionCommitResult, error)
	CompleteUpload(
		ctx context.Context,
		commit CompleteUploadCommit,
	) (CompleteUploadResult, error)
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
