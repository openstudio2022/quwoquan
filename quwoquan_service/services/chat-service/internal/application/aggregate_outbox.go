package application

import (
	"context"
	"time"
)

// AggregateOutboxEvent 是 Conversation / ConversationMembership /
// ConversationUserState 三个聚合共享的事务 outbox 事件形状。事件与聚合
// state、命令回执在同一个 Mongo 事务提交；relay 是唯一投递主线。
type AggregateOutboxEvent struct {
	EventID        string
	EventType      string
	AggregateID    string
	ConversationID string
	ActorID        string
	Payload        map[string]any
	Checkpoint     string
}

// AggregateCommandReceipt 是命名意图命令的幂等回执。目标状态已满足的
// no-op 命令也必须持久化回执（不产生 outbox 事件），后续相同 key 重放
// 原始结果。
type AggregateCommandReceipt struct {
	IdempotencyKey string
	CommandName    string
	CommandDigest  string
	AggregateID    string
	ResultJSON     []byte
	ExpiresAt      time.Time
}

// AggregateCommandStore 在调用方事务闭包内提交回执与 outbox 事件；聚合
// state 写入由调用方在同一事务完成。FindReceipt 在命令入口做重放短路，
// digest 不匹配时返回 ErrAggregateIdempotencyConflict。
type AggregateCommandStore interface {
	FindAggregateCommandReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (resultJSON []byte, found bool, err error)
	CommitAggregateCommand(
		ctx context.Context,
		receipt AggregateCommandReceipt,
		events []AggregateOutboxEvent,
	) error
	// AppendAggregateOutboxEvents 供无公开幂等回执的内部写路径（如服务
	// 间复用的会话创建）在事务内可靠追加事件。
	AppendAggregateOutboxEvents(
		ctx context.Context,
		events []AggregateOutboxEvent,
	) error
}

// AggregateOutboxSource 供 relay 与 projector 以独立 checkpoint 消费同一
// 聚合 outbox。
type AggregateOutboxSource interface {
	ReadAggregateOutboxAfter(
		ctx context.Context,
		checkpoint string,
		limit int,
	) ([]AggregateOutboxEvent, error)
	MarkAggregateOutboxDispatched(
		ctx context.Context,
		eventID string,
		dispatchedAt time.Time,
	) error
}

// ProjectionCheckpointStore 是 chat 域投影/relay consumer 的共享检查点
// 端口，按 consumer 名隔离水位。
type ProjectionCheckpointStore interface {
	LoadProjectionCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveProjectionCheckpoint(ctx context.Context, consumer, checkpoint string) error
}
