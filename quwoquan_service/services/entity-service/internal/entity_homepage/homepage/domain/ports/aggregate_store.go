// Package ports 定义 Homepage 对象专属持久化与具名读取契约。
package ports

import (
	"context"
	"encoding/json"
	"time"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
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
	Aggregate        *homepagemodel.Homepage
	ExpectedVersion  int64
	ActorID          string
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Event            OutboxEvent
}

type CommitResult struct {
	Aggregate *homepagemodel.Homepage
	Replayed  bool
}

type NoopReceipt struct {
	Aggregate        *homepagemodel.Homepage
	ActorID          string
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type AggregateStore interface {
	Load(ctx context.Context, homepageID string) (*homepagemodel.Homepage, bool, error)
	FindByCanonical(ctx context.Context, canonicalEntityID string) (*homepagemodel.Homepage, bool, error)
	FindBySource(ctx context.Context, sourceOwner, sourceEntityRef string) (*homepagemodel.Homepage, bool, error)
	FindReceipt(ctx context.Context, actorID, idempotencyKey, commandName, commandDigest string) (CommitResult, bool, error)
	RecordNoopReceipt(ctx context.Context, receipt NoopReceipt) (CommitResult, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

type ExactLookup struct {
	ID                string
	CanonicalEntityID string
	LookupAlias       string
	SourceOwner       string
	SourceEntityRef   string
}

type SearchQuery struct {
	Query        string
	HomepageType string
	City         string
	Status       string
	Cursor       string
	Limit        int
}

type Page struct {
	Items      []homepagemodel.Snapshot
	NextCursor string
}

// DetailProjection 是 Homepage 主档之外的可重建详情读投影。评分、内容预览、
// 关联圈子与关系边均来自其他对象事实，不得进入 Homepage 写聚合或其 Snapshot。
type DetailProjection struct {
	HomepageID       string
	AverageRating    *float64
	RatingCount      int
	ReviewSummary    *homepagemodel.ReviewSummary
	ContentPreview   []homepagemodel.ContentPreview
	QuestionPreview  []homepagemodel.QuestionPreview
	RelatedGroups    []homepagemodel.RelatedGroup
	RelationEdges    []json.RawMessage
	AssistantContext json.RawMessage
	UpdatedAt        time.Time
}

// DetailProjectionStore 是 HomepageDetailView 的独立读写端口。写端只暴露
// 已有事实消费者需要的窄更新，不允许通过详情投影反向修改 Homepage 主档。
type DetailProjectionStore interface {
	LoadDetailProjection(ctx context.Context, homepageID string) (DetailProjection, bool, error)
	UpsertReviewSummary(
		ctx context.Context,
		homepageID string,
		averageRating *float64,
		ratingCount int,
		highlightTags []string,
		updatedAt time.Time,
	) error
}

// Reader 是 Homepage 的具名读端口：精确解析、搜索、来源对账与 backfill cursor。
type Reader interface {
	FindExact(ctx context.Context, lookup ExactLookup) (homepagemodel.Snapshot, bool, error)
	Search(ctx context.Context, query SearchQuery) (Page, error)
	ListBySourceOwner(ctx context.Context, sourceOwner, cursor string, limit int) (Page, error)
	Scan(ctx context.Context, cursor string, limit int) (Page, error)
	Count(ctx context.Context) (int64, error)
}

type FollowerView struct {
	Count         int
	ViewerFollows bool
}

// FollowerProjectionStore 只保存 user.SubjectFollow 的可重建投影，不属于 Homepage 聚合。
type FollowerProjectionStore interface {
	UpsertFollowerState(ctx context.Context, homepageID, personaID string, following bool, sourceVersion int64, updatedAt time.Time) error
	ResolveFollowerView(ctx context.Context, homepageID, viewerPersonaID string) (FollowerView, error)
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
