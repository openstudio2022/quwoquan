package messaging

import (
	"context"
	"encoding/json"
	"fmt"

	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// InProcessProjectorPublisher 直接消费 Post 事务 outbox 事实并同步投影到进程内
// 读模型。它绕过 DomainEvent 传输信封，以保留 outbox 同事务写入的
// AggregateVersion：带版本的投影 sink（搜索索引、地点索引）需要它给
// 权威对象已不可读时的 tombstone 提供 sourceVersion。
type InProcessProjectorPublisher struct {
	projector ports.Projector
}

func NewInProcessProjectorPublisher(projector ports.Projector) *InProcessProjectorPublisher {
	return &InProcessProjectorPublisher{projector: projector}
}

func (p *InProcessProjectorPublisher) Publish(ctx context.Context, event postports.OutboxEvent) error {
	if p == nil || p.projector == nil {
		return nil
	}
	if event.EventID == "" {
		return fmt.Errorf("post outbox event has no stable event id")
	}
	var payload map[string]any
	if len(event.Payload) > 0 {
		if err := json.Unmarshal(event.Payload, &payload); err != nil {
			return fmt.Errorf("decode post outbox payload: %w", err)
		}
	}
	if payload == nil {
		payload = map[string]any{}
	}
	occurredAt := event.OccurredAt.UTC()
	return p.projector.Project(ctx, ports.ProjectorEvent{
		ID:               event.EventID,
		Type:             event.EventType,
		AggregateType:    event.AggregateType,
		AggregateID:      event.AggregateID,
		AggregateVersion: event.AggregateVersion,
		Payload:          payload,
		OccurredAt:       occurredAt,
	})
}

var _ postports.OutboxPublisher = (*InProcessProjectorPublisher)(nil)
