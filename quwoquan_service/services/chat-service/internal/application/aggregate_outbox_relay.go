package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"
)

// AggregateOutboxRelay 把一个聚合 outbox 的事件按 checkpoint 顺序投递到
// EventPublisher。与 MessageOutboxRelay 同构：发布被 transport 接受且
// dispatched 落盘后才推进 consumer checkpoint，崩溃后从水位续投。
type AggregateOutboxRelay struct {
	source      AggregateOutboxSource
	checkpoints ProjectionCheckpointStore
	publisher   EventPublisher
	consumer    string

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewAggregateOutboxRelay(
	source AggregateOutboxSource,
	checkpoints ProjectionCheckpointStore,
	publisher EventPublisher,
	consumer string,
) *AggregateOutboxRelay {
	return &AggregateOutboxRelay{
		source:      source,
		checkpoints: checkpoints,
		publisher:   publisher,
		consumer:    strings.TrimSpace(consumer),
	}
}

func (r *AggregateOutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.source == nil || r.checkpoints == nil ||
		r.publisher == nil || r.consumer == "" {
		return 0, errors.New("aggregate outbox relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadProjectionCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load %s checkpoint: %w", r.consumer, err)
	}
	events, err := r.source.ReadAggregateOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read %s outbox: %w", r.consumer, err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("aggregate outbox event %s has no checkpoint", event.EventID)
		}
		if err := r.publisher.PublishRecordedDomainEvent(
			ctx,
			event.EventID,
			event.EventType,
			event.ConversationID,
			event.ActorID,
			event.Payload,
		); err != nil {
			return index, fmt.Errorf("publish aggregate outbox event %s: %w", event.EventID, err)
		}
		if err := r.source.MarkAggregateOutboxDispatched(ctx, event.EventID, time.Now().UTC()); err != nil {
			return index, fmt.Errorf("mark aggregate outbox event %s dispatched: %w", event.EventID, err)
		}
		if err := r.checkpoints.SaveProjectionCheckpoint(ctx, r.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save %s checkpoint for %s: %w", r.consumer, event.EventID, err)
		}
	}
	return len(events), nil
}

func (r *AggregateOutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 100 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := r.Drain(ctx, 100); err != nil {
			r.recordFailure(err)
		} else {
			r.recordSuccess()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (r *AggregateOutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil {
		return errors.New("aggregate outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	if r.lastSuccess.IsZero() {
		return fmt.Errorf("aggregate outbox relay %s has not completed a scan", r.consumer)
	}
	if r.lastFailure != nil {
		return fmt.Errorf("aggregate outbox relay %s last failure: %w", r.consumer, r.lastFailure)
	}
	if time.Since(r.lastSuccess) > maxStaleness {
		return fmt.Errorf("aggregate outbox relay %s heartbeat is stale", r.consumer)
	}
	return nil
}

func (r *AggregateOutboxRelay) recordSuccess() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastSuccess = time.Now().UTC()
	r.lastFailure = nil
}

func (r *AggregateOutboxRelay) recordFailure(err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastFailure = err
}
