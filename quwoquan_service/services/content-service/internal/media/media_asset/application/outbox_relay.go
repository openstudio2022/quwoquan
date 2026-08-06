package media

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

// MediaAssetOutboxRelay performs durable handoff before advancing the
// object-owned checkpoint. A failed publish leaves the same event readable on
// the next pass, and downstream consumers deduplicate by eventId.
type MediaAssetOutboxRelay struct {
	reader      mediaports.MediaAssetOutboxReader
	checkpoints mediaports.ProjectionCheckpointStore
	publisher   mediaports.OutboxPublisher
	consumer    string

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewMediaAssetOutboxRelay(
	reader mediaports.MediaAssetOutboxReader,
	checkpoints mediaports.ProjectionCheckpointStore,
	publisher mediaports.OutboxPublisher,
	consumer string,
) (*MediaAssetOutboxRelay, error) {
	consumer = strings.TrimSpace(consumer)
	if reader == nil || checkpoints == nil || publisher == nil || consumer == "" {
		return nil, fmt.Errorf("MediaAsset outbox relay requires reader, checkpoint, publisher and consumer")
	}
	return &MediaAssetOutboxRelay{
		reader: reader, checkpoints: checkpoints,
		publisher: publisher, consumer: consumer,
	}, nil
}

func (relay *MediaAssetOutboxRelay) Drain(
	ctx context.Context,
	limit int,
) (int, error) {
	checkpoint, err := relay.checkpoints.LoadCheckpoint(ctx, relay.consumer)
	if err != nil {
		return 0, fmt.Errorf("load MediaAsset publication checkpoint: %w", err)
	}
	events, err := relay.reader.ReadMediaAssetOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read MediaAsset outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("MediaAsset event %q has no checkpoint", event.EventID)
		}
		if err := relay.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish MediaAsset event %q: %w", event.EventID, err)
		}
		if err := relay.checkpoints.SaveCheckpoint(
			ctx,
			relay.consumer,
			event.Checkpoint,
		); err != nil {
			return index, fmt.Errorf("save MediaAsset publication checkpoint: %w", err)
		}
	}
	return len(events), nil
}

func (relay *MediaAssetOutboxRelay) Run(
	ctx context.Context,
	interval time.Duration,
) error {
	if interval <= 0 {
		interval = time.Second
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
			delay = mediaAssetRetryDelay(interval, consecutiveFailures)
		} else {
			relay.recordSuccess()
			consecutiveFailures = 0
			delay = interval
		}
	}
}

func mediaAssetRetryDelay(base time.Duration, attempt int) time.Duration {
	if base <= 0 {
		base = time.Second
	}
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 6 {
		attempt = 6
	}
	delay := base * time.Duration(1<<(attempt-1))
	if delay > 30*time.Second {
		return 30 * time.Second
	}
	return delay
}

func (relay *MediaAssetOutboxRelay) Healthy(maxStaleness time.Duration) error {
	if relay == nil {
		return fmt.Errorf("MediaAsset outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.mu.RLock()
	defer relay.mu.RUnlock()
	if relay.lastSuccess.IsZero() {
		return fmt.Errorf("MediaAsset outbox relay has not completed a scan")
	}
	if relay.lastFailure != nil {
		return fmt.Errorf("MediaAsset outbox relay last failure: %w", relay.lastFailure)
	}
	if time.Since(relay.lastSuccess) > maxStaleness {
		return fmt.Errorf("MediaAsset outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *MediaAssetOutboxRelay) recordSuccess() {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastSuccess = time.Now().UTC()
	relay.lastFailure = nil
}

func (relay *MediaAssetOutboxRelay) recordFailure(err error) {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastFailure = err
}
