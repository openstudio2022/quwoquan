// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	domaineventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/eventing"
	infraeventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/eventing"
	timelineapplication "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/application"
	timelinemessaging "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/infrastructure/messaging"
)

func TestTravelOutboxRelayPublishesMixedObjectsAndReleasesFailedClaims(t *testing.T) {
	store := &travelRelayStore{events: []domaineventing.ClaimedEvent{
		{Event: validTravelEvent("TripPlan", "event-plan", "TripPlanRevised", "trip-1", 2)},
		{Event: validTravelEvent("TripMoment", "event-moment", "TripMomentChanged", "moment-1", 1)},
	}}
	publisher := &travelRelayPublisher{failuresRemaining: 1}
	relay, err := infraeventing.NewOutboxRelay(store, publisher, "worker-1", time.Minute, nil)
	if err != nil {
		t.Fatal(err)
	}
	if count, err := relay.Drain(t.Context(), 10); err == nil || count != 0 {
		t.Fatalf("failed drain count=%d err=%v", count, err)
	}
	if store.claimedCount() != 0 || len(store.published) != 0 {
		t.Fatalf("failed delivery leaked claims or publication: %+v", store)
	}
	if count, err := relay.Drain(t.Context(), 10); err != nil || count != 2 {
		t.Fatalf("retry drain count=%d err=%v", count, err)
	}
	if len(store.published) != 2 || publisher.published != 2 {
		t.Fatalf("published store=%v publisher=%d", store.published, publisher.published)
	}
	if err := relay.Healthy(time.Minute); err != nil {
		t.Fatalf("relay health: %v", err)
	}
}

func TestTravelTypedStreamDrivesIdempotentTimelineProjectionBeforeAck(t *testing.T) {
	durable := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(rtredis.NewMemoryClient(), durable)
	if err != nil {
		t.Fatal(err)
	}
	publisher, err := infraeventing.NewStreamPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	event := validTravelEvent("TripMoment", "event-moment-1", "TripMomentChanged", "moment-1", 1)
	if err := publisher.Publish(t.Context(), event); err != nil {
		t.Fatal(err)
	}
	if err := publisher.Publish(t.Context(), event); err != nil {
		t.Fatal(err)
	}
	projector := &idempotentProjection{}
	consumer, err := timelinemessaging.NewConsumer(transport, projector, "projection-1", nil)
	if err != nil {
		t.Fatal(err)
	}
	processed, err := consumer.ProcessOnce(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	if processed != 2 || projector.uniqueCount() != 1 {
		t.Fatalf("processed=%d unique projections=%d", processed, projector.uniqueCount())
	}
	if err := consumer.Healthy(time.Minute); err != nil {
		t.Fatalf("consumer health: %v", err)
	}
	remaining, err := transport.ReadDurable(t.Context(), runtimemessaging.StreamReadRequest{
		Stream: domaineventing.TripMomentStream, Group: timelinemessaging.ConsumerGroup,
		Consumer: "audit", Count: 10, Block: 10 * time.Millisecond,
	})
	if err != nil || len(remaining) != 0 {
		t.Fatalf("acked stream remaining=%+v err=%v", remaining, err)
	}
}

func validTravelEvent(source, eventID, eventType, aggregateID string, version int64) domaineventing.Event {
	return domaineventing.Event{
		Source: source, EventID: eventID, EventType: eventType,
		AggregateID: aggregateID, AggregateVersion: version,
		Payload:    map[string]any{"tripId": "trip-1"},
		OccurredAt: time.Date(2026, 8, 2, 18, 0, 0, 0, time.UTC),
	}
}

type travelRelayStore struct {
	mu        sync.Mutex
	events    []domaineventing.ClaimedEvent
	claims    map[string]string
	published map[string]time.Time
}

func (store *travelRelayStore) ClaimPending(
	_ context.Context,
	workerID string,
	_ time.Time,
	_ time.Duration,
	limit int,
) ([]domaineventing.ClaimedEvent, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.claims == nil {
		store.claims = map[string]string{}
	}
	if store.published == nil {
		store.published = map[string]time.Time{}
	}
	result := make([]domaineventing.ClaimedEvent, 0, limit)
	for _, event := range store.events {
		if len(result) >= limit || store.claims[event.EventID] != "" || !store.published[event.EventID].IsZero() {
			continue
		}
		store.claims[event.EventID] = workerID
		event.ClaimedBy = workerID
		result = append(result, event)
	}
	return result, nil
}

func (store *travelRelayStore) MarkPublished(
	_ context.Context,
	event domaineventing.ClaimedEvent,
	workerID string,
	publishedAt time.Time,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.claims[event.EventID] != workerID {
		return errors.New("claim owner mismatch")
	}
	store.published[event.EventID] = publishedAt
	delete(store.claims, event.EventID)
	return nil
}

func (store *travelRelayStore) ReleaseClaims(
	_ context.Context,
	workerID string,
	events []domaineventing.ClaimedEvent,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	for _, event := range events {
		if store.claims[event.EventID] == workerID {
			delete(store.claims, event.EventID)
		}
	}
	return nil
}

func (store *travelRelayStore) claimedCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.claims)
}

type travelRelayPublisher struct {
	failuresRemaining int
	published         int
}

func (publisher *travelRelayPublisher) Publish(_ context.Context, _ domaineventing.Event) error {
	if publisher.failuresRemaining > 0 {
		publisher.failuresRemaining--
		return errors.New("injected publish failure")
	}
	publisher.published++
	return nil
}

type idempotentProjection struct {
	mu      sync.Mutex
	applied map[string]timelineapplication.SourceEvent
}

func (projection *idempotentProjection) Apply(
	_ context.Context,
	event timelineapplication.SourceEvent,
) error {
	projection.mu.Lock()
	defer projection.mu.Unlock()
	if projection.applied == nil {
		projection.applied = map[string]timelineapplication.SourceEvent{}
	}
	projection.applied[event.EventID] = event
	return nil
}

func (projection *idempotentProjection) uniqueCount() int {
	projection.mu.Lock()
	defer projection.mu.Unlock()
	return len(projection.applied)
}
