package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"
)

type LifecycleEvent struct {
	EventID       string
	Type          string
	CircleID      string
	SourceVersion int64
	Checkpoint    string
}

type EventSource interface {
	ReadAfter(context.Context, string, int) ([]LifecycleEvent, error)
}

type CheckpointStore interface {
	Load(context.Context, string) (string, error)
	Save(context.Context, string, string) error
}

type EventHandler interface {
	Apply(context.Context, LifecycleEvent) error
}

type Relay struct {
	source      EventSource
	checkpoints CheckpointStore
	handler     EventHandler
	consumer    string
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewRelay(source EventSource, checkpoints CheckpointStore, handler EventHandler, consumer string) *Relay {
	return &Relay{
		source: source, checkpoints: checkpoints, handler: handler,
		consumer: strings.TrimSpace(consumer),
	}
}

func (relay *Relay) Drain(ctx context.Context, limit int) (int, error) {
	if relay == nil || relay.source == nil || relay.checkpoints == nil || relay.handler == nil || relay.consumer == "" {
		return 0, errors.New("CircleSearchItemView relay is not fully configured")
	}
	checkpoint, err := relay.checkpoints.Load(ctx, relay.consumer)
	if err != nil {
		return 0, fmt.Errorf("load CircleSearchItemView checkpoint: %w", err)
	}
	events, err := relay.source.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read CircleSearchItemView source: %w", err)
	}
	for index, event := range events {
		if event.EventID == "" || event.CircleID == "" || event.SourceVersion <= 0 || event.Checkpoint == "" {
			return index, errors.New("CircleSearchItemView source event is incomplete")
		}
		if err := relay.handler.Apply(ctx, event); err != nil {
			return index, fmt.Errorf("apply CircleSearchItemView event %s: %w", event.EventID, err)
		}
		if err := relay.checkpoints.Save(ctx, relay.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save CircleSearchItemView checkpoint: %w", err)
		}
	}
	return len(events), nil
}

func (relay *Relay) Run(ctx context.Context, interval time.Duration) error {
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

func (relay *Relay) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.mu.RLock()
	defer relay.mu.RUnlock()
	if relay.lastSuccess.IsZero() {
		return errors.New("CircleSearchItemView relay has not completed a scan")
	}
	if relay.lastFailure != nil {
		return relay.lastFailure
	}
	if time.Since(relay.lastSuccess) > maxStaleness {
		return errors.New("CircleSearchItemView relay heartbeat is stale")
	}
	return nil
}

func (relay *Relay) recordSuccess() {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastSuccess, relay.lastFailure = time.Now().UTC(), nil
}

func (relay *Relay) recordFailure(err error) {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	relay.lastFailure = err
}
