package circlepostplacement

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
)

// OutboxRelay gives every CirclePostPlacement sink an independent durable
// checkpoint. A sink failure never advances or shares another sink's waterline.
type OutboxRelay struct {
	reader      placementports.OutboxReader
	checkpoints placementports.ProjectionCheckpointStore
	publisher   placementports.OutboxPublisher
	consumer    string
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewOutboxRelay(reader placementports.OutboxReader, checkpoints placementports.ProjectionCheckpointStore, publisher placementports.OutboxPublisher, consumer string) *OutboxRelay {
	return &OutboxRelay{reader: reader, checkpoints: checkpoints, publisher: publisher, consumer: strings.TrimSpace(consumer)}
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if relay == nil || relay.reader == nil || relay.checkpoints == nil || relay.publisher == nil || relay.consumer == "" {
		return 0, fmt.Errorf("CirclePostPlacement outbox relay is not fully configured")
	}
	checkpoint, err := relay.checkpoints.LoadCheckpoint(ctx, relay.consumer)
	if err != nil {
		return 0, fmt.Errorf("load CirclePostPlacement checkpoint: %w", err)
	}
	events, err := relay.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read CirclePostPlacement outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("CirclePostPlacement event %q has no checkpoint", event.EventID)
		}
		if err := relay.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish CirclePostPlacement event %q: %w", event.EventID, err)
		}
		if err := relay.checkpoints.SaveCheckpoint(ctx, relay.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save CirclePostPlacement checkpoint for %q: %w", event.EventID, err)
		}
	}
	return len(events), nil
}

func (relay *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := relay.Drain(ctx, 100); err != nil {
			relay.recordFailure(err)
			if ctx.Err() != nil {
				return ctx.Err()
			}
		} else {
			relay.recordSuccess()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (relay *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if relay == nil {
		return fmt.Errorf("CirclePostPlacement outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.mu.RLock()
	defer relay.mu.RUnlock()
	if relay.lastSuccess.IsZero() {
		return fmt.Errorf("CirclePostPlacement outbox relay has not completed a scan")
	}
	if relay.lastFailure != nil {
		return fmt.Errorf("CirclePostPlacement outbox relay last failure: %w", relay.lastFailure)
	}
	if time.Since(relay.lastSuccess) > maxStaleness {
		return fmt.Errorf("CirclePostPlacement outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) recordSuccess() {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastSuccess = time.Now().UTC()
	relay.lastFailure = nil
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastFailure = err
}
