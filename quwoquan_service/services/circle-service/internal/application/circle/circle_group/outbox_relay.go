package circlegroup

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	groupports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/ports"
)

type OutboxRelay struct {
	reader      groupports.OutboxReader
	checkpoints groupports.ProjectionCheckpointStore
	publisher   groupports.OutboxPublisher
	consumer    string
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewOutboxRelay(reader groupports.OutboxReader, checkpoints groupports.ProjectionCheckpointStore, publisher groupports.OutboxPublisher, consumer string) *OutboxRelay {
	return &OutboxRelay{reader: reader, checkpoints: checkpoints, publisher: publisher, consumer: strings.TrimSpace(consumer)}
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if relay == nil || relay.reader == nil || relay.checkpoints == nil || relay.publisher == nil || relay.consumer == "" {
		return 0, fmt.Errorf("CircleGroup outbox relay is not fully configured")
	}
	checkpoint, err := relay.checkpoints.LoadCheckpoint(ctx, relay.consumer)
	if err != nil {
		return 0, fmt.Errorf("load CircleGroup checkpoint: %w", err)
	}
	events, err := relay.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read CircleGroup outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("CircleGroup event %q has no checkpoint", event.EventID)
		}
		if err := relay.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish CircleGroup event %q: %w", event.EventID, err)
		}
		if err := relay.checkpoints.SaveCheckpoint(ctx, relay.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save CircleGroup checkpoint for %q: %w", event.EventID, err)
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
		return fmt.Errorf("CircleGroup outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.mu.RLock()
	defer relay.mu.RUnlock()
	if relay.lastSuccess.IsZero() {
		return fmt.Errorf("CircleGroup outbox relay has not completed a scan")
	}
	if relay.lastFailure != nil {
		return fmt.Errorf("CircleGroup outbox relay last failure: %w", relay.lastFailure)
	}
	if time.Since(relay.lastSuccess) > maxStaleness {
		return fmt.Errorf("CircleGroup outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) recordSuccess() {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastSuccess, relay.lastFailure = time.Now().UTC(), nil
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastFailure = err
}
