// Package mediaprocessing 是 content-service 内的独立媒体处理功能模块。
//
// 模块边界（可解耦约束）：worker 只依赖本文件声明的窄端口——outbox 读取、
// 资产快照、视频处理器、处理结果回写与 checkpoint。今后拆分为独立
// media-processing 服务时，ResultRecorder 换成调用
// `POST /internal/content/media/{mediaId}:processing-result` 的 HTTP 客户端、
// OutboxSource/CheckpointStore 换成跨服务消费实现即可，worker 编排逻辑零改动。
package mediaprocessing

import (
	"context"
	"fmt"
	"time"

	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/content/post/domain/media/ports"
)

// OutboxSource reads durable media facts after a checkpoint. The production
// implementation is the media Mongo outbox reader.
type OutboxSource interface {
	ReadMediaOutboxAfter(
		ctx context.Context,
		checkpoint string,
		limit int,
	) ([]mediaports.OutboxEvent, error)
}

// AssetSnapshotLoader loads the authoritative MediaAsset aggregate so the
// worker can decide idempotently whether processing is still required.
type AssetSnapshotLoader interface {
	LoadMediaAsset(
		ctx context.Context,
		assetID string,
	) (*mediamodel.MediaAsset, bool, error)
}

// CheckpointStore persists the worker consumer offset. Delivery-then-save
// ordering keeps the pipeline at-least-once; RecordMediaProcessingResult 的
// command digest 幂等与 processing 态守卫吸收重放。
type CheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer string, checkpoint string) error
}

// CheckpointLeaseStore serializes one consumer across content-service
// replicas. A lease owner must renew while FFmpeg is active, and advancing the
// cursor must atomically prove ownership so a stale worker cannot skip facts
// after a failover. The same narrow port is implementable by a future
// standalone worker's durable cursor store.
type CheckpointLeaseStore interface {
	TryAcquireMediaProcessingLease(
		ctx context.Context,
		consumer string,
		owner string,
		now time.Time,
		ttl time.Duration,
	) (bool, error)
	RenewMediaProcessingLease(
		ctx context.Context,
		consumer string,
		owner string,
		now time.Time,
		ttl time.Duration,
	) (bool, error)
	SaveMediaProcessingCheckpointWithLease(
		ctx context.Context,
		consumer string,
		owner string,
		checkpoint string,
		now time.Time,
		ttl time.Duration,
	) (bool, error)
}

// PoisonEvent is a durable, non-retriable source record that was isolated so
// one corrupt aggregate reference cannot permanently stall later media facts.
// It deliberately excludes the raw event payload because outbox payloads can
// contain user-controlled metadata; repair is driven by the immutable event
// identity and checkpoint only.
type PoisonEvent struct {
	Consumer      string
	EventID       string
	EventType     string
	AggregateType string
	AggregateID   string
	Checkpoint    string
	OccurredAt    time.Time
	Reason        string
	QuarantinedAt time.Time
}

// PoisonEventRecorder persists a quarantined event before its checkpoint can
// advance. Its implementation must be idempotent by (consumer, eventID).
// A persistence failure is an infrastructure failure and must retain the
// checkpoint for retry.
type PoisonEventRecorder interface {
	QuarantineMediaProcessingEvent(ctx context.Context, event PoisonEvent) error
}

type ArtifactCleanupWork struct {
	WorkID            string
	PublicSliceKeys   []string
	PublicPrefixes    []string
	PrivateObjectKeys []string
	PrivatePrefixes   []string
}

// ArtifactCleanupStore projects a deleted MediaAsset into a retryable,
// namespace-bounded cleanup unit. The tombstone remains the durable work
// source until MarkMediaAssetArtifactsDeleted succeeds.
type ArtifactCleanupStore interface {
	PrepareMediaAssetArtifactCleanup(
		ctx context.Context,
		assetID string,
		eventID string,
	) (ArtifactCleanupWork, bool, error)
	MarkMediaAssetArtifactsDeleted(
		ctx context.Context,
		assetID string,
		workID string,
	) error
}

type ArtifactReclaimer interface {
	ReclaimMediaArtifacts(
		ctx context.Context,
		publicSliceKeys []string,
		publicPrefixes []string,
		privateObjectKeys []string,
		privatePrefixes []string,
	) error
}

// ResultRecorder applies the trusted processing outcome to the MediaAsset
// aggregate. In-process it is the media application facade; a future
// standalone worker service replaces it with the internal HTTP operation.
type ResultRecorder interface {
	RecordMediaProcessingResult(
		ctx context.Context,
		command mediaapp.RecordMediaProcessingResultCommand,
	) (mediaapp.MediaAssetCommandResult, error)
}

// ProcessRequest describes one visual MediaAsset awaiting trusted processing.
type ProcessRequest struct {
	AssetID string
	// AssetVersion is the aggregate version the processing result will be
	// applied to (current version + 1). Delivery slice keys embed it so a
	// re-processed asset can never silently overwrite an older delivery set.
	AssetVersion int64
	// SourceObjectKey is the private CAS object key of the uploaded bytes.
	SourceObjectKey string
	MediaType       string
	MimeType        string
	FileSize        int64
}

// ProcessOutcome is the trusted worker output bound to one asset version.
type ProcessOutcome struct {
	Descriptor mediamodel.MediaProcessingDescriptor
}

// RejectionError marks a content-level failure (corrupt bytes, duration over
// the ceiling, no decodable video stream). The worker records the asset as
// rejected and advances; infrastructure failures return ordinary errors and
// are retried without advancing the checkpoint.
type RejectionError struct {
	Reason string
}

func (e *RejectionError) Error() string {
	return fmt.Sprintf("media processing rejected: %s", e.Reason)
}

// Processor turns uploaded image/video bytes into their normalized delivery
// artifacts and a typed descriptor. Routing is internal to the processor so
// the worker retains one lifecycle and checkpoint path.
type Processor interface {
	Process(ctx context.Context, request ProcessRequest) (ProcessOutcome, error)
}

// Observer receives worker lifecycle signals for metrics. Implementations
// live in infrastructure; a nil observer is valid.
type Observer interface {
	JobCompleted(
		mediaType string,
		inputSizeClass string,
		result string,
		duration time.Duration,
	)
	BatchObserved(eventCount int, batchLimit int)
	OutboxOldestEventAge(age time.Duration)
	CompleteToReady(
		mediaType string,
		inputSizeClass string,
		duration time.Duration,
	)
	Poisoned(reason string, eventAge time.Duration)
	PoisonQuarantineFailed(reason string)
}
