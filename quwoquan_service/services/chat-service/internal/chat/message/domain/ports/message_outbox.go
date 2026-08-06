package ports

import (
	"context"
	"time"
)

// OutboxEvent 是与 Message 聚合状态在同一个 Mongo 事务内提交的发件箱记录。
// Checkpoint 是 relay 推进 consumer 水位的唯一依据；Status 记录投递状态，
// dispatched 落盘后才允许推进水位。
type OutboxEvent struct {
	EventID        string
	EventType      string
	ConversationID string
	ActorID        string
	Payload        map[string]any
	Status         string
	Checkpoint     string
}

// OutboxReader 供 relay 与收件箱投影按 checkpoint 顺序读取已提交事件。
type OutboxReader interface {
	ReadMessageOutboxAfter(
		ctx context.Context,
		checkpoint string,
		limit int,
	) ([]OutboxEvent, error)
}

// OutboxDispatchStore 记录事件已被 transport 接受，保证崩溃后不重复推进水位。
type OutboxDispatchStore interface {
	MarkMessageOutboxDispatched(
		ctx context.Context,
		eventID string,
		dispatchedAt time.Time,
	) error
}

// OutboxCheckpointStore 按 consumer 名隔离水位，一个失败的 sink 不会推进
// 另一个 sink 的水位。
type OutboxCheckpointStore interface {
	LoadMessageOutboxCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveMessageOutboxCheckpoint(ctx context.Context, consumer, checkpoint string) error
}
