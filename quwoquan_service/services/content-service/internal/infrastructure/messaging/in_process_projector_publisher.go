package messaging

import (
	"context"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/content-service/internal/application/ports"
)

// InProcessProjectorPublisher 将领域事件同步投影到进程内读模型。
type InProcessProjectorPublisher struct {
	projector ports.Projector
}

func NewInProcessProjectorPublisher(projector ports.Projector) *InProcessProjectorPublisher {
	return &InProcessProjectorPublisher{projector: projector}
}

func (p *InProcessProjectorPublisher) Publish(ctx context.Context, event runtimemessaging.DomainEvent) error {
	if p == nil || p.projector == nil {
		return nil
	}
	occurredAt, err := time.Parse(time.RFC3339, event.OccurredAt)
	if err != nil || occurredAt.IsZero() {
		occurredAt = time.Now().UTC()
	}
	payload := event.Payload
	if payload == nil {
		payload = map[string]any{}
	}
	return p.projector.Project(ctx, ports.ProjectorEvent{
		Type:          event.Type,
		AggregateType: event.AggregateType,
		AggregateID:   event.AggregateID,
		Payload:       payload,
		OccurredAt:    occurredAt,
	})
}
