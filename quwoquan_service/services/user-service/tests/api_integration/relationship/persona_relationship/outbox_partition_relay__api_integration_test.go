// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-004
package api_integration

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/mq"
	relapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
	relpersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

type poisonRelationshipTransport struct {
	runtimemessaging.MessageTransport
	poisonEventID string
}

func (transport *poisonRelationshipTransport) AppendDurable(
	ctx context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	for _, field := range message.Fields {
		if field.Name == "eventId" && field.Value == transport.poisonEventID {
			return "", errors.New("poison transport record")
		}
	}
	return transport.MessageTransport.AppendDurable(ctx, message)
}

func TestPersonaRelationshipPartitionRelayFencesOldWorkerAndIsolatesPoisonOnRealPostgresRedis(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		redisRuntime, err := testinfra.StartRealRedis(ctx)
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = redisRuntime.Close(context.Background()) })
		router := platformredis.MustNewRouter(rtredis.RouterConfig{
			Scenes: map[string]rtredis.SceneConfig{"general": {
				Mode: "standalone", Addr: redisRuntime.Addr, Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
			}}, DefaultScene: "general",
		})
		t.Cleanup(func() { _ = router.Close() })
		client := router.Scene("general")
		baseTransport, err := runtimemessaging.NewRedisMessageTransport(client, client)
		if err != nil {
			t.Fatal(err)
		}

		store := relpersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)
		type row struct {
			eventID     string
			partitionID int
			sequence    int64
		}
		rowsByPartition := map[int][]row{}
		for index := 0; len(rowsByPartition) < 2; index++ {
			target := fmt.Sprintf("partition-target-%d", index)
			if _, err := followRelationship(t, ctx, service, "partition-source", target, "test", fmt.Sprintf("partition-key-%d", index)); err != nil {
				t.Fatal(err)
			}
			var current row
			if err := pool.QueryRow(ctx, `
				SELECT event_id, partition_id, partition_sequence
				FROM persona_relationship_outbox
				ORDER BY occurred_at DESC, event_id DESC LIMIT 1`,
			).Scan(&current.eventID, &current.partitionID, &current.sequence); err != nil {
				t.Fatal(err)
			}
			rowsByPartition[current.partitionID] = append(rowsByPartition[current.partitionID], current)
			if index > 5000 {
				t.Fatal("failed to generate two partitions")
			}
		}

		var sequencePartitions int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM persona_relationship_outbox_sequences`).Scan(&sequencePartitions); err != nil {
			t.Fatal(err)
		}
		if sequencePartitions < 2 {
			t.Fatalf("partition sequence rows=%d, want at least 2", sequencePartitions)
		}

		oldLeases, err := store.ClaimOutboxPartitions(ctx, "fence-proof", "old", time.Millisecond, relports.PersonaRelationshipOutboxPartitionCount)
		if err != nil {
			t.Fatal(err)
		}
		time.Sleep(10 * time.Millisecond)
		newLeases, err := store.ClaimOutboxPartitions(ctx, "fence-proof", "new", time.Minute, relports.PersonaRelationshipOutboxPartitionCount)
		if err != nil {
			t.Fatal(err)
		}
		newLease := populatedRelationshipLease(t, ctx, store, newLeases)
		var oldLease relports.OutboxPartitionLease
		for _, lease := range oldLeases {
			if lease.PartitionID == newLease.PartitionID {
				oldLease = lease
				break
			}
		}
		facts, err := store.ReadOutboxPartition(ctx, newLease, 1)
		if err != nil || len(facts) != 1 {
			t.Fatalf("read new lease facts=%d err=%v", len(facts), err)
		}
		if err := store.AdvanceOutboxCheckpoint(ctx, oldLease, facts[0]); !errors.Is(err, relports.ErrOutboxLeaseLost) {
			t.Fatalf("old worker advanced checkpoint: %v", err)
		}

		poisonPartition := facts[0].PartitionID
		poisonEventID := facts[0].Event.EventID
		transport := &poisonRelationshipTransport{MessageTransport: baseTransport, poisonEventID: poisonEventID}
		relay := relapp.NewOutboxRelay(store, mq.NewEventPublisher(transport))
		drained, err := relay.Drain(ctx, 100)
		if err == nil || drained == 0 {
			t.Fatalf("drained=%d err=%v; other partition must continue", drained, err)
		}
		var poisonSequence int64
		if err := pool.QueryRow(ctx, `
			SELECT sequence FROM persona_relationship_outbox_checkpoints
			WHERE consumer=$1 AND partition_id=$2`,
			"persona-relationship-runtime-events", poisonPartition,
		).Scan(&poisonSequence); err != nil {
			t.Fatal(err)
		}
		if poisonSequence != 0 {
			t.Fatalf("poison partition checkpoint=%d, want 0", poisonSequence)
		}
		messages, err := client.XRead(ctx, map[string]string{mq.PersonaRelationshipEventStream: "0-0"}, 100, 0)
		if err != nil || len(messages) == 0 {
			t.Fatalf("read Redis transport messages=%d err=%v", len(messages), err)
		}
		for _, message := range messages {
			if message.Values["eventId"] == poisonEventID {
				t.Fatal("poison event was ACKed into Redis")
			}
			if message.Values["partitionKey"] != message.Values["pairId"] ||
				message.Values["partitionId"] == "" || message.Values["partitionSequence"] == "" {
				t.Fatalf("transport envelope=%v", message.Values)
			}
			if _, err := strconv.Atoi(message.Values["partitionId"]); err != nil {
				t.Fatalf("partitionId=%q", message.Values["partitionId"])
			}
		}
	})
}

func populatedRelationshipLease(
	t *testing.T,
	ctx context.Context,
	store relports.PartitionedPersonaRelationshipOutbox,
	leases []relports.OutboxPartitionLease,
) relports.OutboxPartitionLease {
	t.Helper()
	for _, lease := range leases {
		facts, err := store.ReadOutboxPartition(ctx, lease, 1)
		if err == nil && len(facts) > 0 {
			return lease
		}
	}
	t.Fatal("no populated partition lease")
	return relports.OutboxPartitionLease{}
}
