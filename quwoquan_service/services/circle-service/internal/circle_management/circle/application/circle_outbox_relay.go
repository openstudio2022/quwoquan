package application

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	messaging "quwoquan_service/runtime/messaging"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
)

// CircleOutboxRelay 把 Circle 本体 outbox 事实投递给下游 sink（search projector、
// 缓存失效等）。失败的 sink 不推进 checkpoint，与其余 6 个对象 relay 同范式。
type CircleOutboxRelay struct {
	reader      circleports.OutboxReader
	checkpoints circleports.ProjectionCheckpointStore
	publisher   circleports.OutboxPublisher
	consumer    string
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewCircleOutboxRelay(
	reader circleports.OutboxReader,
	checkpoints circleports.ProjectionCheckpointStore,
	publisher circleports.OutboxPublisher,
	consumer string,
) *CircleOutboxRelay {
	return &CircleOutboxRelay{
		reader: reader, checkpoints: checkpoints,
		publisher: publisher, consumer: strings.TrimSpace(consumer),
	}
}

func (relay *CircleOutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if relay == nil || relay.reader == nil || relay.checkpoints == nil || relay.publisher == nil || relay.consumer == "" {
		return 0, fmt.Errorf("Circle outbox relay is not fully configured")
	}
	checkpoint, err := relay.checkpoints.LoadCheckpoint(ctx, relay.consumer)
	if err != nil {
		return 0, fmt.Errorf("load Circle checkpoint: %w", err)
	}
	events, err := relay.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read Circle outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("Circle event %q has no checkpoint", event.EventID)
		}
		if err := relay.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish Circle event %q: %w", event.EventID, err)
		}
		if err := relay.checkpoints.SaveCheckpoint(ctx, relay.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save Circle checkpoint for %q: %w", event.EventID, err)
		}
	}
	return len(events), nil
}

func (relay *CircleOutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}
	delay := time.Duration(0)
	consecutiveFailures := 0
	for {
		if delay > 0 {
			timer := time.NewTimer(delay)
			select {
			case <-ctx.Done():
				timer.Stop()
				return ctx.Err()
			case <-timer.C:
			}
		}
		if _, err := relay.Drain(ctx, 100); err != nil {
			relay.recordFailure(err)
			if ctx.Err() != nil {
				return ctx.Err()
			}
			consecutiveFailures++
			delay = circleOutboxRetryDelay(interval, consecutiveFailures)
		} else {
			relay.recordSuccess()
			consecutiveFailures = 0
			delay = interval
		}
	}
}

func circleOutboxRetryDelay(base time.Duration, attempt int) time.Duration {
	if base <= 0 {
		base = 250 * time.Millisecond
	}
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 7 {
		attempt = 7
	}
	delay := base * time.Duration(1<<(attempt-1))
	if delay > 30*time.Second {
		return 30 * time.Second
	}
	return delay
}

func (relay *CircleOutboxRelay) Healthy(maxStaleness time.Duration) error {
	if relay == nil {
		return fmt.Errorf("Circle outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.mu.RLock()
	defer relay.mu.RUnlock()
	if relay.lastSuccess.IsZero() {
		return fmt.Errorf("Circle outbox relay has not completed a scan")
	}
	if relay.lastFailure != nil {
		return fmt.Errorf("Circle outbox relay last failure: %w", relay.lastFailure)
	}
	if time.Since(relay.lastSuccess) > maxStaleness {
		return fmt.Errorf("Circle outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *CircleOutboxRelay) recordSuccess() {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastSuccess, relay.lastFailure = time.Now().UTC(), nil
}

func (relay *CircleOutboxRelay) recordFailure(err error) {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastFailure = err
}

// CircleDomainEventSink 把 Circle outbox 事实转换为 runtime DomainEvent
// 后交给既有 messaging.EventPublisher 消费（如 search projector），
// 使搜索投影与聚合状态经同一事务事实驱动。
type CircleDomainEventSink struct {
	publisher messaging.EventPublisher
}

func NewCircleDomainEventSink(publisher messaging.EventPublisher) *CircleDomainEventSink {
	if publisher == nil {
		panic("CircleDomainEventSink requires publisher")
	}
	return &CircleDomainEventSink{publisher: publisher}
}

func (sink *CircleDomainEventSink) Publish(ctx context.Context, event circleports.OutboxEvent) error {
	var payload map[string]any
	if len(event.Payload) > 0 {
		if err := json.Unmarshal(event.Payload, &payload); err != nil {
			return fmt.Errorf("decode Circle outbox payload %q: %w", event.EventID, err)
		}
	}
	return sink.publisher.Publish(ctx, messaging.DomainEvent{
		Type:          event.EventType,
		AggregateType: "Circle",
		AggregateID:   event.AggregateID,
		Payload:       payload,
		OccurredAt:    event.OccurredAt.UTC().Format(time.RFC3339),
	})
}

var _ circleports.OutboxPublisher = (*CircleDomainEventSink)(nil)
