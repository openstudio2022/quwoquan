package ports

import (
	"context"
	"encoding/json"
	"time"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
	tombstoneports "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/ports"
)

// OutboxEvent 是 Post 聚合变更与版本提交同事务写入的不可变事实。
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateType    string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	// Checkpoint is populated by OutboxReader. It is opaque to consumers and
	// must be persisted verbatim after the event has been applied.
	Checkpoint string
}

// PostDeletionTombstone 是 DeletePost 命令的伴随不可变事实
// （canonical object content.DeletedPostTombstone）。它与聚合提交同事务
// 持久化到 deleted_post_tombstones，_id 复用 postId 作唯一 dedupe key；
// 保留期由 expireAt TTL 索引承载。
type PostDeletionTombstone = tombstonemodel.Tombstone

// Commit 是 PostCommandFacade 交给 PostAggregateStore 的唯一写模型。
// ExpectedVersion=0 仅用于创建；其余命令必须携带已装载版本。
// Tombstone 仅在删除命令时非空，与 state/receipt/outbox 同事务追加。
type Commit struct {
	Post             *postmodel.Post
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
	Tombstone        *PostDeletionTombstone
}

type CommitResult struct {
	Post     *postmodel.Post
	Replayed bool
}

// AggregateStore 只负责 Post 聚合版本、幂等 receipt 与同库 outbox 的原子提交。
type AggregateStore interface {
	Load(ctx context.Context, postID string) (*postmodel.Post, bool, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

// DetailReader 是 Post detail/card/presentation 的具名读端口。
type DetailReader interface {
	FindByID(ctx context.Context, postID string) (*postmodel.Post, bool)
	FindByPublicationIntent(
		ctx context.Context,
		authorID string,
		publishIntentID string,
	) (*postmodel.Post, bool)
}

// CollectionReader 承担 Post 自有的 author-page 与重建扫描 Slice。
type CollectionReader interface {
	ListAll(ctx context.Context) ([]postmodel.Post, error)
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
	ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post
}

// CounterStore 只承载可重建的必要计数，不作为互动成员关系真相源。
type CounterStore interface {
	AdjustCommentCount(ctx context.Context, postID string, delta int64) (int64, bool, error)
	SetCommentCount(ctx context.Context, postID string, count int64) (bool, error)
}

// OutboxReader 为异步 projection worker 提供可重放事件流。
type OutboxReader interface {
	ReadAfter(ctx context.Context, checkpoint string, limit int) ([]OutboxEvent, error)
}

// OutboxPublisher is an infrastructure boundary for delivering durable Post
// facts. The relay owns retry and checkpoint progress; it must not be called
// from an aggregate command before Commit succeeds.
type OutboxPublisher interface {
	Publish(ctx context.Context, event OutboxEvent) error
}

// ProjectionCheckpointStore 保存 Post 读模型消费者自己的重放水位。
type ProjectionCheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error
}

// TombstoneReader 是删除保留期语义的具名读端口：保留期内返回墓碑事实
// （读取方据此回 410 content_deleted），TTL 到期后 found=false 回落 404。
type TombstoneReader interface {
	FindTombstone(
		ctx context.Context,
		postID string,
	) (PostDeletionTombstone, bool, error)
}

type TombstoneStore = tombstoneports.Store
