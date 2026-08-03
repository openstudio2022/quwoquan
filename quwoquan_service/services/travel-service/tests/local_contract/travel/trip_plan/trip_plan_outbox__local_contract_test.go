// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
)

func TestTripPlanOutboxRelayLeasesRetriesAndMarksOnlyPublishedEvents(t *testing.T) {
	store := &relayStore{events: []ports.OutboxEvent{
		{EventID: "event-1", EventType: "TripPlanCreated", AggregateID: "trip-1", AggregateVersion: 1, OccurredAt: time.Now()},
		{EventID: "event-2", EventType: "TripPlanRevised", AggregateID: "trip-1", AggregateVersion: 2, OccurredAt: time.Now()},
	}}
	publisher := &relayPublisher{failuresRemaining: 1}
	relay, err := application.NewOutboxRelay(store, publisher, "travel-worker-1", time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if count, err := relay.Drain(t.Context(), 10); err == nil || count != 0 {
		t.Fatalf("first drain count=%d err=%v", count, err)
	}
	if len(store.published) != 0 || len(store.claims) != 0 {
		t.Fatalf("failed publish must release claims and publish nothing: %+v", store)
	}
	if count, err := relay.Drain(t.Context(), 10); err != nil || count != 2 {
		t.Fatalf("retry drain count=%d err=%v", count, err)
	}
	if len(store.published) != 2 || publisher.published != 2 {
		t.Fatalf("store published=%v publisher=%d", store.published, publisher.published)
	}
	if err := relay.Healthy(time.Minute); err != nil {
		t.Fatalf("healthy relay: %v", err)
	}
}

type relayStore struct {
	mu        sync.Mutex
	events    []ports.OutboxEvent
	claims    map[string]string
	published map[string]time.Time
}

func (store *relayStore) ClaimPendingOutbox(
	_ context.Context,
	workerID string,
	_ time.Time,
	_ time.Duration,
	limit int,
) ([]ports.ClaimedOutboxEvent, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.claims == nil {
		store.claims = map[string]string{}
	}
	if store.published == nil {
		store.published = map[string]time.Time{}
	}
	result := make([]ports.ClaimedOutboxEvent, 0, limit)
	for _, event := range store.events {
		if len(result) >= limit || !store.published[event.EventID].IsZero() || store.claims[event.EventID] != "" {
			continue
		}
		store.claims[event.EventID] = workerID
		result = append(result, ports.ClaimedOutboxEvent{OutboxEvent: event, ClaimedBy: workerID})
	}
	return result, nil
}

func (store *relayStore) MarkOutboxPublished(
	_ context.Context,
	eventID string,
	workerID string,
	publishedAt time.Time,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.claims[eventID] != workerID {
		return errors.New("claim owner mismatch")
	}
	store.published[eventID] = publishedAt
	delete(store.claims, eventID)
	return nil
}

func (store *relayStore) ReleaseOutboxClaims(
	_ context.Context,
	workerID string,
	eventIDs []string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	for _, eventID := range eventIDs {
		if store.claims[eventID] == workerID {
			delete(store.claims, eventID)
		}
	}
	return nil
}

type relayPublisher struct {
	failuresRemaining int
	published         int
}

func (publisher *relayPublisher) Publish(_ context.Context, _ ports.OutboxEvent) error {
	if publisher.failuresRemaining > 0 {
		publisher.failuresRemaining--
		return errors.New("injected publisher failure")
	}
	publisher.published++
	return nil
}
