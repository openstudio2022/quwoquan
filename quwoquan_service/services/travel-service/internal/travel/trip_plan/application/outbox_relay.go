package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
)

type OutboxRelay struct {
	store     ports.OutboxStore
	publisher ports.EventPublisher
	workerID  string
	lease     time.Duration

	healthMu      sync.RWMutex
	lastSuccessAt time.Time
	lastError     error
}

func NewOutboxRelay(
	store ports.OutboxStore,
	publisher ports.EventPublisher,
	workerID string,
	lease time.Duration,
) (*OutboxRelay, error) {
	if store == nil || publisher == nil || strings.TrimSpace(workerID) == "" || lease <= 0 {
		return nil, errors.New("TripPlan outbox relay configuration is incomplete")
	}
	return &OutboxRelay{
		store: store, publisher: publisher,
		workerID: strings.TrimSpace(workerID), lease: lease,
	}, nil
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	now := time.Now().UTC()
	events, err := relay.store.ClaimPendingOutbox(
		ctx, relay.workerID, now, relay.lease, limit,
	)
	if err != nil {
		relay.recordFailure(err)
		return 0, fmt.Errorf("claim TripPlan outbox: %w", err)
	}
	claimedIDs := make([]string, 0, len(events))
	for _, event := range events {
		claimedIDs = append(claimedIDs, event.EventID)
	}
	for index, event := range events {
		if err := relay.publisher.Publish(ctx, event.OutboxEvent); err != nil {
			_ = relay.store.ReleaseOutboxClaims(ctx, relay.workerID, claimedIDs[index:])
			relay.recordFailure(err)
			return index, fmt.Errorf("publish TripPlan outbox %s: %w", event.EventID, err)
		}
		if err := relay.store.MarkOutboxPublished(
			ctx, event.EventID, relay.workerID, time.Now().UTC(),
		); err != nil {
			_ = relay.store.ReleaseOutboxClaims(ctx, relay.workerID, claimedIDs[index:])
			relay.recordFailure(err)
			return index, fmt.Errorf("mark TripPlan outbox %s published: %w", event.EventID, err)
		}
	}
	relay.recordSuccess(time.Now().UTC())
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
			return err
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

func (relay *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	relay.healthMu.RLock()
	defer relay.healthMu.RUnlock()
	if relay.lastError != nil {
		return relay.lastError
	}
	if relay.lastSuccessAt.IsZero() ||
		(maxStaleness > 0 && time.Since(relay.lastSuccessAt) > maxStaleness) {
		return errors.New("TripPlan outbox relay has no recent successful scan")
	}
	return nil
}

func (relay *OutboxRelay) recordSuccess(at time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessAt = at
	relay.lastError = nil
	relay.healthMu.Unlock()
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastError = err
	relay.healthMu.Unlock()
}
