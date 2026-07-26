package post

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const defaultPostOutboxConsumer = "content-runtime-fanout"

// OutboxRelay is the only Post event delivery path. It advances the durable
// consumer checkpoint only after an event publisher has accepted the fact.
// Commands never project or publish before their aggregate/outbox transaction
// has committed.
type OutboxRelay struct {
	reader      postports.OutboxReader
	checkpoints postports.ProjectionCheckpointStore
	publisher   postports.OutboxPublisher
	consumer    string
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewOutboxRelay(
	reader postports.OutboxReader,
	checkpoints postports.ProjectionCheckpointStore,
	publisher postports.OutboxPublisher,
	consumer string,
) *OutboxRelay {
	return &OutboxRelay{
		reader:      reader,
		checkpoints: checkpoints,
		publisher:   publisher,
		consumer:    defaultPostOutboxConsumerIfEmpty(consumer),
	}
}

func defaultPostOutboxConsumerIfEmpty(consumer string) string {
	if consumer = strings.TrimSpace(consumer); consumer != "" {
		return consumer
	}
	return defaultPostOutboxConsumer
}

// Drain delivers at most limit durable facts. It returns the count that was
// checkpointed; a failed publish leaves the failed event and following events
// eligible for replay.
func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.reader == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, fmt.Errorf("post outbox relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load post outbox checkpoint: %w", err)
	}
	events, err := r.reader.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read post outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("post outbox event %q has no checkpoint", event.EventID)
		}
		if err := r.publisher.Publish(ctx, event); err != nil {
			return index, fmt.Errorf("publish post outbox event %q: %w", event.EventID, err)
		}
		if err := r.checkpoints.SaveCheckpoint(ctx, r.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf(
				"save post outbox checkpoint for event %q: %w",
				event.EventID,
				err,
			)
		}
	}
	return len(events), nil
}

// Run drains durable facts until the application context ends. A failed batch
// is retried after interval without advancing its checkpoint.
func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		if _, err := r.Drain(ctx, 100); err != nil {
			r.RecordFailure(err)
			if ctx.Err() != nil {
				return ctx.Err()
			}
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-ticker.C:
				continue
			}
		}
		r.RecordSuccess()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

// Healthy reports whether the relay has recently completed a durable scan
// without a newer failure. It is intended for the production readiness
// boundary, not for triggering delivery work.
func (r *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil {
		return fmt.Errorf("post outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	if r.lastSuccess.IsZero() {
		return fmt.Errorf("post outbox relay has not completed a scan")
	}
	if r.lastFailure != nil {
		return fmt.Errorf("post outbox relay last failure: %w", r.lastFailure)
	}
	if time.Since(r.lastSuccess) > maxStaleness {
		return fmt.Errorf(
			"post outbox relay heartbeat is stale: %s",
			time.Since(r.lastSuccess).Round(time.Millisecond),
		)
	}
	return nil
}

func (r *OutboxRelay) RecordSuccess() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastSuccess = time.Now().UTC()
	r.lastFailure = nil
}

func (r *OutboxRelay) RecordFailure(err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastFailure = err
}
