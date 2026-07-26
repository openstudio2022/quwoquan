// Package ports 定义 Circle 聚合本体专属的持久化契约。
package ports

import (
	"context"
	"encoding/json"
	"time"

	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
)

type CommitRequest struct {
	Change           circlemodel.ChangeSet
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type CommitReceipt struct {
	CircleID string
	Version  int64
	Status   circlemodel.CircleStatus
	Replayed bool
}

// NoopReceipt 持久化"目标状态已满足"的命名意图回执：
// 不递增聚合 version、不产生 outbox 事件，后续相同 key 重放原始结果。
type NoopReceipt struct {
	CircleID         string
	Version          int64
	Status           circlemodel.CircleStatus
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

// AggregateStore 只负责 Circle 状态、命令回执、CAS 与事务 outbox。
type AggregateStore interface {
	Load(context.Context, string) (circlemodel.Circle, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
	RecordNoopReceipt(context.Context, NoopReceipt) (CommitReceipt, error)
}

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	Checkpoint       string
}

type OutboxReader interface {
	ReadAfter(context.Context, string, int) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(context.Context, string) (string, error)
	SaveCheckpoint(context.Context, string, string) error
}

type OutboxPublisher interface {
	Publish(context.Context, OutboxEvent) error
}

// MembershipRoleReader 是命令权限校验用的具名跨对象读端口。
type MembershipRoleReader interface {
	ReadMembershipRole(ctx context.Context, circleID, personaID string) (role string, state string, found bool, err error)
}

// CacheInvalidator 在聚合提交后失效 Redis 详情缓存；失败仅结构化告警。
type CacheInvalidator interface {
	InvalidateCircle(ctx context.Context, circleID string) error
}
