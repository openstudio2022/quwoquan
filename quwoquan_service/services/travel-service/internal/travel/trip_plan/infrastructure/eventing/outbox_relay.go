package eventing

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	domaineventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/eventing"
)

type OutboxRelay struct {
	store     domaineventing.OutboxStore
	publisher domaineventing.Publisher
	workerID  string
	lease     time.Duration
	logger    *slog.Logger

	mu          sync.RWMutex
	lastScan    time.Time
	lastFailure error
}

func NewOutboxRelay(
	store domaineventing.OutboxStore,
	publisher domaineventing.Publisher,
	workerID string,
	lease time.Duration,
	logger *slog.Logger,
) (*OutboxRelay, error) {
	workerID = strings.TrimSpace(workerID)
	if store == nil || publisher == nil || workerID == "" || lease <= 0 {
		return nil, errors.New("Travel outbox relay configuration is incomplete")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &OutboxRelay{
		store: store, publisher: publisher, workerID: workerID, lease: lease, logger: logger,
	}, nil
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	events, err := relay.store.ClaimPending(
		ctx, relay.workerID, time.Now().UTC(), relay.lease, limit,
	)
	if err != nil {
		relay.record(err)
		return 0, fmt.Errorf("claim Travel outbox: %w", err)
	}
	for index, event := range events {
		if err := relay.publisher.Publish(ctx, event.Event); err != nil {
			_ = relay.store.ReleaseClaims(ctx, relay.workerID, events[index:])
			relay.record(err)
			return index, fmt.Errorf("publish Travel outbox %s: %w", event.EventID, err)
		}
		if err := relay.store.MarkPublished(
			ctx, event, relay.workerID, time.Now().UTC(),
		); err != nil {
			_ = relay.store.ReleaseClaims(ctx, relay.workerID, events[index:])
			relay.record(err)
			return index, fmt.Errorf("mark Travel outbox %s published: %w", event.EventID, err)
		}
	}
	relay.record(nil)
	return len(events), nil
}

func (relay *OutboxRelay) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			relay.logger.ErrorContext(ctx, "Travel outbox relay failed", slog.String("error", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (relay *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	relay.mu.RLock()
	defer relay.mu.RUnlock()
	if relay.lastScan.IsZero() {
		return errors.New("Travel outbox relay has not completed a scan")
	}
	if relay.lastFailure != nil {
		return relay.lastFailure
	}
	if time.Since(relay.lastScan) > maxStaleness {
		return errors.New("Travel outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) record(err error) {
	relay.mu.Lock()
	relay.lastScan = time.Now().UTC()
	relay.lastFailure = err
	relay.mu.Unlock()
}
