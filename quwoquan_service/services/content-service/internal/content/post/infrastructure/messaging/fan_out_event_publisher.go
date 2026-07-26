package messaging

import (
	"context"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

// FanOutEventPublisher 将同一领域事件扇出到多个 EventPublisher。
type FanOutEventPublisher struct {
	publishers []runtimemessaging.EventPublisher
}

func NewFanOutEventPublisher(publishers ...runtimemessaging.EventPublisher) *FanOutEventPublisher {
	filtered := make([]runtimemessaging.EventPublisher, 0, len(publishers))
	for _, publisher := range publishers {
		if publisher != nil {
			filtered = append(filtered, publisher)
		}
	}
	return &FanOutEventPublisher{publishers: filtered}
}

func (p *FanOutEventPublisher) Publish(ctx context.Context, event runtimemessaging.DomainEvent) error {
	var firstErr error
	for _, publisher := range p.publishers {
		if err := publisher.Publish(ctx, event); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	return firstErr
}
