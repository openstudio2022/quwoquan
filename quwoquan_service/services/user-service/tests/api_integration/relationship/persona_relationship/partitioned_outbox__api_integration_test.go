package api_integration

import (
	"context"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
	"testing"
	"time"
)

type partitionPublisher struct {
	poison    string
	published []string
}

func (p *partitionPublisher) PublishPersonaRelationship(_ context.Context, e relmodel.OutboxEvent) error {
	if e.EventID == p.poison {
		return errors.New("poison")
	}
	p.published = append(p.published, e.EventID)
	return nil
}
func TestPersonaRelationshipPartitionLeaseAndPoisonIsolationRealPostgres(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)
		for i := 0; i < 12; i++ {
			target := fmt.Sprintf("partition-target-%d", i)
			if _, err := followRelationship(t, ctx, service, "partition-source", target, "test", fmt.Sprintf("partition-key-%d", i)); err != nil {
				t.Fatal(err)
			}
		}
		leases1, err := store.ClaimOutboxPartitions(ctx, "lease-test", "worker-1", time.Millisecond, relports.PersonaRelationshipOutboxPartitionCount)
		if err != nil {
			t.Fatal(err)
		}
		time.Sleep(10 * time.Millisecond)
		leases2, err := store.ClaimOutboxPartitions(ctx, "lease-test", "worker-2", time.Minute, relports.PersonaRelationshipOutboxPartitionCount)
		if err != nil {
			t.Fatal(err)
		}
		var oldLease, newLease relports.OutboxPartitionLease
		var event relports.PartitionedOutboxEvent
		found := false
		for _, next := range leases2 {
			events, readErr := store.ReadOutboxPartition(ctx, next, 10)
			if readErr == nil && len(events) > 0 {
				newLease = next
				event = events[0]
				for _, old := range leases1 {
					if old.PartitionID == next.PartitionID {
						oldLease = old
						found = true
						break
					}
				}
				if found {
					break
				}
			}
		}
		if !found {
			t.Fatal("no claimed populated partition")
		}
		if err := store.AdvanceOutboxCheckpoint(ctx, oldLease, event); !errors.Is(err, relports.ErrOutboxLeaseLost) {
			t.Fatalf("old lease err=%v", err)
		}
		if err := store.AdvanceOutboxCheckpoint(ctx, newLease, event); err != nil {
			t.Fatal(err)
		}
		var poisonEvent string
		var poisonPartition int
		rows, err := pool.Query(ctx, `SELECT event_id,partition_id FROM persona_relationship_outbox WHERE published_at IS NULL ORDER BY partition_id,partition_sequence`)
		if err != nil {
			t.Fatal(err)
		}
		defer rows.Close()
		if rows.Next() {
			if err := rows.Scan(&poisonEvent, &poisonPartition); err != nil {
				t.Fatal(err)
			}
		}
		if poisonEvent == "" {
			t.Fatal("missing poison event")
		}
		publisher := &partitionPublisher{poison: poisonEvent}
		relay := relationshipapp.NewOutboxRelay(store, publisher)
		_, _ = relay.Drain(ctx, 100)
		var poisonSequence int64
		if err := pool.QueryRow(ctx, `SELECT sequence FROM persona_relationship_outbox_checkpoints WHERE consumer='persona-relationship-runtime-events' AND partition_id=$1`, poisonPartition).Scan(&poisonSequence); err != nil {
			t.Fatal(err)
		}
		if poisonSequence != 0 {
			t.Fatalf("poison partition advanced=%d", poisonSequence)
		}
		if len(publisher.published) == 0 {
			t.Fatal("poison partition blocked every other partition")
		}
	})
}
