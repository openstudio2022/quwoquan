package ports

import (
	"context"
	"errors"
	"time"

	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
)

var (
	ErrGatheringSafetyAuthorizationNotFound = errors.New("Gathering safety authorization not found")
	ErrGatheringSafetyAuthorizationDenied   = errors.New("Gathering safety authorization denied")
	ErrGatheringSafetyAuthorizationConflict = errors.New("Gathering safety authorization conflict")
)

const GatheringSafetyActionTerminate = "terminate_gathering"

type GatheringSafetyAuthorization struct {
	ActorPersonaID  string
	GatheringID     string
	Action          string
	EvidenceRef     string
	DecisionRef     string
	DecisionVersion int64
	DecisionDigest  string
	ExpiresAt       time.Time
	IssuedAt        time.Time
	RevokedAt       time.Time
}

type IssueGatheringSafetyAuthorizationRequest struct {
	ReportID              string
	ExpectedReportVersion int64
	ActorPersonaID        string
	ExpiresAt             time.Time
	IdempotencyKey        string
}

type RevokeGatheringSafetyAuthorizationRequest struct {
	ReportID       string
	DecisionRef    string
	IdempotencyKey string
	RevokedAt      time.Time
}

// GatheringSafetyAuthorityStore is Report's canonical short-lived authority
// owner. Reads must return the current revocation and expiry state.
type GatheringSafetyAuthorityStore interface {
	IssueGatheringSafetyAuthorization(
		context.Context,
		IssueGatheringSafetyAuthorizationRequest,
	) (GatheringSafetyAuthorization, bool, error)
	RevokeGatheringSafetyAuthorization(
		context.Context,
		RevokeGatheringSafetyAuthorizationRequest,
	) (GatheringSafetyAuthorization, bool, error)
	ReadGatheringSafetyAuthorization(
		context.Context,
		string,
	) (GatheringSafetyAuthorization, bool, error)
}

// OutboxCheckpoint 是 Report outbox 全序中的不透明水位。消费者只能持久化
// Reader 附在 OutboxEvent 上的值，不能自行拼接或解释。
type OutboxCheckpoint string

// OutboxEvent 是 Report 聚合与状态变更同事务提交的事实。
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	Checkpoint       OutboxCheckpoint
}

// Commit 只承载 Report 聚合提交所需的并发、幂等和事实信息。
type Commit struct {
	Aggregate        *reportmodel.Report
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []OutboxEvent
}

type CommitResult struct {
	Aggregate *reportmodel.Report
	Replayed  bool
}

// NoopReceipt 是目标状态已满足的命名迁移的持久化回执：不递增 aggregate
// version、不产生 outbox 事实，但后续同 key 重放必须返回本次结果。
type NoopReceipt struct {
	Aggregate        *reportmodel.Report
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

// AggregateStore 是 Report command facet 唯一允许依赖的持久化端口。
// FindReceipt 必须在状态迁移前检查，以保证重复命令不会因已完成的迁移而被误判为非法。
type AggregateStore interface {
	Load(ctx context.Context, reportID string) (*reportmodel.Report, bool, error)
	FindReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (CommitResult, bool, error)
	RecordNoopReceipt(ctx context.Context, receipt NoopReceipt) (CommitResult, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

// OutboxReader 为后台 relay 提供按稳定全序可重放的 Report 事实。checkpoint
// 由上一条已确认事件提供，Reader 绝不能依赖请求内状态。
type OutboxReader interface {
	ReadAfter(
		ctx context.Context,
		checkpoint OutboxCheckpoint,
		limit int,
	) ([]OutboxEvent, error)
}

// ProjectionCheckpointStore 为每个独立 consumer 创建排他的 checkpoint
// lease。一个 lease 在 Commit 前不会暴露其中的推进；失败路径必须 Rollback，
// 从而保留至少一次重放语义。
type ProjectionCheckpointStore interface {
	AcquireCheckpoint(
		ctx context.Context,
		consumer string,
	) (ProjectionCheckpointLease, bool, error)
}

// ProjectionCheckpointLease 绑定一个 consumer 的持久化水位与排他锁。
// acquired=false 表示同一 consumer 正在由另一 relay 实例处理，并非成功
// checkpoint 或可跳过的事件。
type ProjectionCheckpointLease interface {
	Checkpoint() OutboxCheckpoint
	SaveCheckpoint(context.Context, OutboxCheckpoint) error
	Commit(context.Context) error
	Rollback() error
}

// OutboxPublisher 是将已经提交的 Report 事实发送到外部投递通道的基础设施
// 边界。聚合 command 不得直接调用它；relay 在 outbox transaction 完成后才可
// 发布，并只在 publisher 接受事实后推进 checkpoint。
type OutboxPublisher interface {
	Publish(context.Context, OutboxEvent) error
}
