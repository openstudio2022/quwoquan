// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/design.md#dec-008
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-004
package api_integration

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	relevent "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/event"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	relprojection "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/projection"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestRelationshipStatisticsLedgerReplayUnlikeRollupAndRepairRealPostgres(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		projector := relprojection.NewCounterProjector(pool, nil)
		rollup := relprojection.NewStatisticsRollup(pool)
		now := time.Now().UTC().Truncate(time.Microsecond)
		follow := relationshipStatisticsEvent("follow-1", relevent.PersonaFollowStateChanged, 1, true, now)
		if err := projector.Apply(ctx, follow); err != nil {
			t.Fatal(err)
		}
		if err := projector.Apply(ctx, follow); err != nil {
			t.Fatalf("replay must be idempotent: %v", err)
		}
		assertRelationshipStatisticsBucket(t, ctx, pool, "persona-a", "following", 1)
		assertRelationshipStatisticsBucket(t, ctx, pool, "persona-b", "follower", 1)

		unfollow := relationshipStatisticsEvent("unfollow-2", relevent.PersonaFollowStateChanged, 2, false, now.Add(time.Second))
		if err := projector.Apply(ctx, unfollow); err != nil {
			t.Fatal(err)
		}
		assertRelationshipStatisticsBucket(t, ctx, pool, "persona-a", "following", 0)
		assertRelationshipStatisticsBucket(t, ctx, pool, "persona-b", "follower", 0)

		if _, _, err := rollup.Rollup(ctx); err != nil {
			t.Fatal(err)
		}
		slice, err := rollup.Read(ctx, "persona-a")
		if err != nil || slice.State != relprojection.StatisticsAvailable || slice.Snapshot == nil || slice.Snapshot.FollowingCount != 0 {
			t.Fatalf("unexpected persona statistics slice=%+v err=%v", slice, err)
		}

		if _, err := pool.Exec(ctx, `UPDATE persona_relationship_statistics_buckets SET value=7 WHERE generation='live' AND persona_id='persona-a' AND contribution_kind='following'`); err != nil {
			t.Fatal(err)
		}
		repair := relprojection.NewCounterReconciler(pool, nil)
		result, err := repair.ReconcileBatch(ctx, "", 100)
		if err != nil || result.Repaired == 0 {
			t.Fatalf("repair result=%+v err=%v", result, err)
		}
		assertRelationshipStatisticsBucket(t, ctx, pool, "persona-a", "following", 0)
	})
}

func TestRelationshipStatisticsRejectsSameVersionDifferentDigestRealPostgres(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		projector := relprojection.NewCounterProjector(pool, nil)
		now := time.Now().UTC()
		first := relationshipStatisticsEvent("event-1", relevent.PersonaFollowStateChanged, 1, true, now)
		if err := projector.Apply(ctx, first); err != nil {
			t.Fatal(err)
		}
		drift := relationshipStatisticsEvent("event-2", relevent.PersonaFollowStateChanged, 1, false, now)
		if err := projector.Apply(ctx, drift); err == nil {
			t.Fatal("same member version with different after-state must fail")
		}
	})
}

func relationshipStatisticsEvent(eventID, eventName string, version int64, following bool, occurredAt time.Time) relmodel.OutboxEvent {
	return relmodel.OutboxEvent{
		EventID: eventID, EventName: eventName,
		Payload: relmodel.OutboxPayload{
			PairID: "pair-statistics", SourcePersonaID: "persona-a", TargetPersonaID: "persona-b",
			Following: following, Version: version, OccurredAt: occurredAt,
		},
	}
}

func assertRelationshipStatisticsBucket(t *testing.T, ctx context.Context, pool *pgxpool.Pool, personaID, kind string, want int64) {
	t.Helper()
	var got int64
	if err := pool.QueryRow(ctx, `SELECT COALESCE(SUM(value),0) FROM persona_relationship_statistics_buckets WHERE generation='live' AND persona_id=$1 AND contribution_kind=$2`, personaID, kind).Scan(&got); err != nil {
		t.Fatal(err)
	}
	if got != want {
		t.Fatalf("relationship statistics %s/%s=%d want=%d", personaID, kind, got, want)
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-004
func TestRelationshipStatisticsReaderCutoverRefusesRollbackThatWouldLoseNewFacts(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		projector := relprojection.NewCounterProjector(pool, nil)
		rollup := relprojection.NewStatisticsRollup(pool)
		now := time.Now().UTC()
		if err := projector.Apply(ctx, relationshipStatisticsEvent("cutover-1", relevent.PersonaFollowStateChanged, 1, true, now)); err != nil {
			t.Fatal(err)
		}
		g1, _, err := rollup.Rollup(ctx)
		if err != nil {
			t.Fatal(err)
		}
		if err := projector.Apply(ctx, relationshipStatisticsEvent("cutover-2", relevent.PersonaFollowStateChanged, 2, false, now.Add(time.Second))); err != nil {
			t.Fatal(err)
		}
		g2, _, err := rollup.Rollup(ctx)
		if err != nil {
			t.Fatal(err)
		}
		if err := rollup.SwitchReaderGeneration(ctx, g2, g1, "2"); err == nil {
			t.Fatal("unsafe rollback accepted")
		}
		if err := rollup.SwitchReaderGeneration(ctx, g2, g1, "2"); err == nil {
			t.Fatal("repeated unsafe rollback accepted")
		}
		if err := rollup.SwitchReaderGeneration(ctx, g2, g2, "2"); err != nil {
			t.Fatalf("idempotent cutover rehearsal: %v", err)
		}
		slice, err := rollup.Read(ctx, "persona-a")
		if err != nil || slice.Snapshot == nil || slice.Snapshot.Generation != g2 || slice.Snapshot.FollowingCount != 0 {
			t.Fatalf("slice=%+v err=%v", slice, err)
		}
	})
}

func TestRelationshipStatisticsBackfillRehearsalIsRepeatableAndKeepsLaterFacts(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)
		result, err := followRelationship(t, ctx, service, "backfill-source", "backfill-target", "rehearsal", "backfill-follow")
		if err != nil {
			t.Fatal(err)
		}
		if _, err := pool.Exec(ctx, `DELETE FROM persona_relationship_statistics_members;DELETE FROM persona_relationship_statistics_buckets;DELETE FROM persona_relationship_statistics_rollups;DELETE FROM persona_relationship_statistics_reader_generation`); err != nil {
			t.Fatal(err)
		}
		repair := relprojection.NewCounterReconciler(pool, nil)
		w1, err := repair.BackfillAuthoritySnapshot(ctx)
		if err != nil {
			t.Fatal(err)
		}
		w2, err := repair.BackfillAuthoritySnapshot(ctx)
		if err != nil || w2 != w1 {
			t.Fatalf("repeat watermark %q/%q err=%v", w1, w2, err)
		}
		assertRelationshipStatisticsBucket(t, ctx, pool, "backfill-source", "following", 1)
		rollup := relprojection.NewStatisticsRollup(pool)
		g1, _, err := rollup.Rollup(ctx)
		if err != nil {
			t.Fatal(err)
		}
		event := relationshipStatisticsEvent("backfill-unfollow", relevent.PersonaFollowStateChanged, result.State.Version+1, false, time.Now().UTC())
		event.Payload.PairID = result.State.PairID
		if err := relprojection.NewCounterProjector(pool, nil).Apply(ctx, event); err != nil {
			t.Fatal(err)
		}
		g2, _, err := rollup.Rollup(ctx)
		if err != nil {
			t.Fatal(err)
		}
		if err := rollup.SwitchReaderGeneration(ctx, g2, g1, fmt.Sprintf("%d", event.Payload.Version)); err == nil {
			t.Fatal("rollback lost post-backfill fact")
		}
	})
}
