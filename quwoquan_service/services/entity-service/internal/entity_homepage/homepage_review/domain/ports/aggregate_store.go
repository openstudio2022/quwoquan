// Package ports 定义 HomepageReview 专属的持久化契约。
package ports

import (
	"context"
	"time"

	reviewmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/model"
)

// OutboxEvent 是与 HomepageReview 聚合版本在同一事务提交的不可变事实。
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
}

type Commit struct {
	Aggregate        *reviewmodel.HomepageReview
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
}

type CommitResult struct {
	Aggregate *reviewmodel.HomepageReview
	Replayed  bool
}

type NoopReceipt struct {
	Aggregate        *reviewmodel.HomepageReview
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

// AggregateStore 只负责 HomepageReview 状态、命令回执、CAS 与事务 outbox；
// Homepage 侧摘要投影由 outbox consumer 异步推进。
type AggregateStore interface {
	Load(ctx context.Context, reviewID string) (*reviewmodel.HomepageReview, bool, error)
	FindByAuthor(
		ctx context.Context,
		homepageID string,
		authorPersonaID string,
	) (*reviewmodel.HomepageReview, bool, error)
	FindReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (CommitResult, bool, error)
	RecordNoopReceipt(ctx context.Context, receipt NoopReceipt) (CommitResult, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

type PageRequest struct {
	Cursor string
	Limit  int
}

type Page struct {
	Items      []reviewmodel.Snapshot
	NextCursor string
}

type Summary struct {
	AverageRating *float64
	RatingCount   int
	HighlightTags []string
}

// PageReader 是主页评价列表的具名读端口（active 过滤，createdAt desc keyset）。
type PageReader interface {
	ListByHomepage(
		ctx context.Context,
		homepageID string,
		request PageRequest,
	) (Page, error)
}

type SummaryReader interface {
	SummarizeByHomepage(ctx context.Context, homepageID string) (Summary, error)
}

// OutboxReader 供 Homepage 评价摘要投影按 checkpoint 重放评价事实。
type OutboxReader interface {
	ReadAfter(ctx context.Context, checkpoint string, limit int) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error
}
