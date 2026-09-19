// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-004
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	relapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

type relationshipPartitionStore struct {
	leases      []relports.OutboxPartitionLease
	events      map[int][]relports.PartitionedOutboxEvent
	checkpoints map[int]int64
}

func (s *relationshipPartitionStore) ClaimOutboxPartitions(context.Context, string, string, time.Duration, int) ([]relports.OutboxPartitionLease, error) {
	return append([]relports.OutboxPartitionLease(nil), s.leases...), nil
}
func (s *relationshipPartitionStore) ReadOutboxPartition(_ context.Context, lease relports.OutboxPartitionLease, _ int) ([]relports.PartitionedOutboxEvent, error) {
	return append([]relports.PartitionedOutboxEvent(nil), s.events[lease.PartitionID]...), nil
}
func (s *relationshipPartitionStore) AdvanceOutboxCheckpoint(_ context.Context, lease relports.OutboxPartitionLease, event relports.PartitionedOutboxEvent) error {
	if event.PartitionSequence != s.checkpoints[lease.PartitionID]+1 {
		return relports.ErrOutboxLeaseLost
	}
	s.checkpoints[lease.PartitionID] = event.PartitionSequence
	return nil
}

type relationshipPartitionPublisher struct {
	poison string
	mu     sync.Mutex
	seen   []string
}

func (p *relationshipPartitionPublisher) PublishPersonaRelationship(_ context.Context, event relmodel.OutboxEvent) error {
	p.mu.Lock()
	p.seen = append(p.seen, event.EventID)
	p.mu.Unlock()
	if event.EventID == p.poison {
		return errors.New("poison event")
	}
	return nil
}

func TestPersonaRelationshipRelayIsolatesPoisonPartitionAndKeepsContinuousCheckpoint(t *testing.T) {
	leases := []relports.OutboxPartitionLease{
		{Consumer: "test", Owner: "worker", PartitionID: 3, LeaseEpoch: 1},
		{Consumer: "test", Owner: "worker", PartitionID: 9, LeaseEpoch: 1},
	}
	makeEvent := func(partition int, sequence int64, eventID string) relports.PartitionedOutboxEvent {
		return relports.PartitionedOutboxEvent{
			PartitionKey: fmt.Sprintf("pair-%d", partition), PartitionID: partition,
			PartitionSequence: sequence,
			Event:             relmodel.OutboxEvent{EventID: eventID, EventName: "PersonaFollowStateChanged"},
		}
	}
	store := &relationshipPartitionStore{
		leases: leases, checkpoints: map[int]int64{},
		events: map[int][]relports.PartitionedOutboxEvent{
			3: {makeEvent(3, 1, "poison"), makeEvent(3, 2, "blocked-successor")},
			9: {makeEvent(9, 1, "healthy")},
		},
	}
	publisher := &relationshipPartitionPublisher{poison: "poison"}
	drained, err := relapp.NewOutboxRelay(store, publisher).Drain(context.Background(), 10)
	if err == nil {
		t.Fatal("poison event must surface a drain error")
	}
	if drained != 1 || store.checkpoints[3] != 0 || store.checkpoints[9] != 1 {
		t.Fatalf("drained=%d checkpoints=%v", drained, store.checkpoints)
	}
	seen := map[string]bool{}
	for _, eventID := range publisher.seen {
		seen[eventID] = true
	}
	if !seen["poison"] || !seen["healthy"] || seen["blocked-successor"] {
		t.Fatalf("seen=%v; poison successor must not publish while healthy partition continues", publisher.seen)
	}
}
