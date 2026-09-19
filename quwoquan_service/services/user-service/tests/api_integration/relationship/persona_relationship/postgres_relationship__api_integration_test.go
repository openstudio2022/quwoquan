// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: follow-user-api
// readiness_case: unfollow-user-api
// readiness_case: list-following-api
// readiness_case: list-followers-api
// readiness_case: get-relationship-api
// readiness_case: get-relationship-capability-api
// readiness_case: block-user-api
// readiness_case: unblock-user-api
// readiness_case: list-blocked-users-api
package api_integration

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestPersonaRelationshipPostgresFollowReplayAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)
		evidence := relationshipEvidence(t, ctx, service, "persona-a", "persona-b", "relationship-follow-key", relmodel.CommandFollow)
		first, err := followWithEvidence(ctx, service, "persona-a", "persona-b", "homepage", evidence)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := followWithEvidence(ctx, service, "persona-a", "persona-b", "homepage", evidence)
		if err != nil || !replayed.IdempotentReplay || replayed.State.Version != first.State.Version {
			t.Fatalf("PersonaRelationship replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM persona_relationship_outbox`).Scan(&outboxCount); err != nil || outboxCount != 1 {
			t.Fatalf("PersonaRelationship outbox=%d err=%v", outboxCount, err)
		}
	})
}

func TestPersonaRelationshipPostgresOperationsShareOneAggregate(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)
		for _, personaID := range []string{"viewer-persona", "target-persona"} {
			if err := usersupport.SeedAccountPersona(ctx, pool, "owner-"+personaID, personaID); err != nil {
				t.Fatal(err)
			}
		}
		if result, err := followRelationship(t, ctx, service, "viewer-persona", "target-persona", "homepage", "follow-operation-key"); err != nil || !result.State.IsFollowing {
			t.Fatalf("FollowUser result=%+v err=%v", result, err)
		}
		state, err := service.GetRelationship(ctx, "viewer-persona", "target-persona")
		if err != nil || !state.IsFollowing {
			t.Fatalf("GetRelationship state=%+v err=%v", state, err)
		}
		following, _, err := service.ListFollowing(ctx, "viewer-persona", "", 20, "viewer-persona", "")
		if err != nil || len(following) != 1 || following[0].TargetPersonaID != "target-persona" {
			t.Fatalf("ListFollowing items=%+v err=%v", following, err)
		}
		followers, _, err := service.ListFollowers(ctx, "target-persona", "", 20, "viewer-persona", "")
		if err != nil || len(followers) != 1 || followers[0].SourcePersonaID != "viewer-persona" {
			t.Fatalf("ListFollowers items=%+v err=%v", followers, err)
		}
		capability := relationshipapp.NewRelationshipCapabilityView(
			relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer-persona",
				TargetPersonaID: "target-persona",
				Relationship:    state,
			},
		)
		if capability.CanFollow || !capability.CanUnfollow {
			t.Fatalf("GetRelationshipCapability view=%+v", capability)
		}
		if result, err := unfollowRelationship(t, ctx, service, "viewer-persona", "target-persona", "unfollow-operation-key"); err != nil || result.State.IsFollowing {
			t.Fatalf("UnfollowUser result=%+v err=%v", result, err)
		}
		if result, err := blockRelationship(t, ctx, service, "viewer-persona", "target-persona", "block-operation-key"); err != nil || !result.State.IsBlocked {
			t.Fatalf("BlockUser result=%+v err=%v", result, err)
		}
		blocked, _, err := service.ListBlocked(ctx, "viewer-persona", "", 20)
		if err != nil || len(blocked) != 1 || blocked[0].TargetPersonaID != "target-persona" {
			t.Fatalf("ListBlockedUsers items=%+v err=%v", blocked, err)
		}
		if result, err := unblockRelationship(t, ctx, service, "viewer-persona", "target-persona", "unblock-operation-key"); err != nil || result.State.IsBlocked {
			t.Fatalf("UnblockUser result=%+v err=%v", result, err)
		}
		var receiptCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM persona_relationship_command_receipts`).Scan(&receiptCount); err != nil || receiptCount != 4 {
			t.Fatalf("PersonaRelationship receipts=%d err=%v", receiptCount, err)
		}
	})
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-006
func TestPersonaRelationshipCommandArbitrationOnRealPostgres(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)

		t.Run("command without idempotency key is refused before any write", func(t *testing.T) {
			if _, err := followRelationship(t, ctx, service, "arb-source", "arb-target", "homepage", "  "); err == nil {
				t.Fatal("empty idempotency key must be refused, not silently receipt-less")
			}
			var rows int
			if err := pool.QueryRow(ctx,
				`SELECT COUNT(*) FROM persona_relationship_directions
				 WHERE source_persona_id='arb-source'`,
			).Scan(&rows); err != nil {
				t.Fatal(err)
			}
			if rows != 0 {
				t.Fatalf("refused command wrote %d directions", rows)
			}
		})

		t.Run("newly accepted no-op advances the version fence without a business event", func(t *testing.T) {
			const (
				source = "noop-source"
				target = "noop-target"
			)
			followed, err := followRelationship(t, ctx, service, source, target, "homepage", "noop-follow")
			if err != nil || !followed.Changed {
				t.Fatalf("seed follow result=%+v err=%v", followed, err)
			}
			eventsAfterFollow := relationshipOutboxCount(t, ctx, pool, source, target)

			repeat, err := followRelationship(t, ctx, service, source, target, "homepage", "noop-follow-again")
			if err != nil {
				t.Fatalf("no-op follow err=%v", err)
			}
			if repeat.Changed {
				t.Fatal("repeat follow must not report a business change")
			}
			if repeat.State.Version <= followed.State.Version {
				t.Fatalf(
					"newly accepted no-op must advance the version fence: follow=%d no-op=%d",
					followed.State.Version, repeat.State.Version,
				)
			}
			if got := relationshipOutboxCount(t, ctx, pool, source, target); got != eventsAfterFollow {
				t.Fatalf("no-op emitted business events: before=%d after=%d", eventsAfterFollow, got)
			}
			if repeat.Outcome != relmodel.OutcomeCommitted {
				t.Fatalf("no-op outcome=%q, want committed", repeat.Outcome)
			}
		})

		t.Run("stale expectedVersion cannot overtake a newer decision", func(t *testing.T) {
			const (
				source = "cas-source"
				target = "cas-target"
			)
			first, err := followRelationship(t, ctx, service, source, target, "homepage", "cas-follow")
			if err != nil {
				t.Fatal(err)
			}
			staleVersion := first.State.Version - 1
			if _, err := store.Apply(ctx, relmodel.Command{
				Kind:            relmodel.CommandUnfollow,
				SourcePersonaID: source,
				TargetPersonaID: target,
				IdempotencyKey:  "cas-stale-unfollow",
				MutationBasis:   "direct-test-basis",
				AcceptUntil:     time.Now().UTC().Add(time.Hour),
				ExpectedVersion: &staleVersion,
			}); !errors.Is(err, relmodel.ErrVersionConflict) {
				t.Fatalf("stale expectedVersion err=%v, want version conflict", err)
			}
			state, err := service.GetRelationship(ctx, source, target)
			if err != nil || !state.IsFollowing {
				t.Fatalf("rejected CAS changed state: %+v err=%v", state, err)
			}
		})

		t.Run("expire finalize and the original write produce exactly one terminal winner", func(t *testing.T) {
			const (
				source = "finalize-source"
				target = "finalize-target"
				key    = "finalize-key"
			)
			finalized, err := store.FinalizeExpired(ctx, source, key, relmodel.CommandFollow, target, time.Now().UTC().Add(-time.Minute))
			if err != nil {
				t.Fatalf("FinalizeExpired err=%v", err)
			}
			if finalized.Outcome != relmodel.OutcomeExpired {
				t.Fatalf("finalize outcome=%q, want expired", finalized.Outcome)
			}
			// 终结已赢得仲裁：同键原写不能再执行，也不能被伪造成功。
			if _, err := followRelationship(t, ctx, service, source, target, "homepage", key); err == nil {
				t.Fatal("original write after finalize must fail, not commit")
			}
			state, err := service.GetRelationship(ctx, source, target)
			if err != nil {
				t.Fatal(err)
			}
			if state.IsFollowing {
				t.Fatal("finalized-as-not-executed command must leave no relationship")
			}
			var outcome string
			if err := pool.QueryRow(ctx, `
				SELECT outcome FROM persona_relationship_command_receipts
				WHERE actor_persona_id=$1 AND idempotency_key=$2`,
				source, key,
			).Scan(&outcome); err != nil {
				t.Fatal(err)
			}
			if outcome != string(relmodel.OutcomeExpired) {
				t.Fatalf("receipt outcome=%q, want expired", outcome)
			}
		})

		t.Run("committed receipt retains at least the accept window plus recovery slack", func(t *testing.T) {
			const (
				source = "retention-source"
				target = "retention-target"
				key    = "retention-key"
			)
			if _, err := followRelationship(t, ctx, service, source, target, "homepage", key); err != nil {
				t.Fatal(err)
			}
			var retentionHours float64
			if err := pool.QueryRow(ctx, `
				SELECT EXTRACT(EPOCH FROM (expires_at - created_at)) / 3600
				FROM persona_relationship_command_receipts
				WHERE actor_persona_id=$1 AND idempotency_key=$2`,
				source, key,
			).Scan(&retentionHours); err != nil {
				t.Fatal(err)
			}
			if retentionHours < 96 {
				t.Fatalf("receipt retention = %.2fh, want at least 96h", retentionHours)
			}
		})

		t.Run("same key with a different command is a conflict", func(t *testing.T) {
			const key = "shared-key-different-command"
			if _, err := followRelationship(t, ctx, service, "conflict-source", "conflict-target-a", "homepage", key); err != nil {
				t.Fatal(err)
			}
			if _, err := followRelationship(t, ctx, service, "conflict-source", "conflict-target-b", "homepage", key); err == nil {
				t.Fatal("same key with a different target must conflict")
			}
			state, err := service.GetRelationship(ctx, "conflict-source", "conflict-target-b")
			if err != nil || state.IsFollowing {
				t.Fatalf("conflicting command leaked state: %+v err=%v", state, err)
			}
		})
	})
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-005
func TestPersonaRelationshipPairIdentityIntegrityOnRealPostgres(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)

		const (
			realSource = "integrity-source"
			realTarget = "integrity-target"
		)
		if _, err := followRelationship(t, ctx, service, realSource, realTarget, "homepage", "integrity-follow"); err != nil {
			t.Fatal(err)
		}
		realPair, err := relmodel.NewPair(realSource, realTarget)
		if err != nil {
			t.Fatal(err)
		}

		t.Run("a digest hit whose identity tuple differs is refused", func(t *testing.T) {
			// 人工制造摘要碰撞：把另一对身份写进同一个 pair_id。
			writeEvidence := relationshipEvidence(t, ctx, service, realSource, realTarget, "integrity-collision-write", relmodel.CommandFollow)
			unsetEvidence := relationshipEvidence(t, ctx, service, realSource, realTarget, "integrity-collision-unfollow", relmodel.CommandUnfollow)
			const (
				collidedLower = "integrity-collided-lower"
				collidedUpper = "integrity-collided-upper"
			)
			if _, err := pool.Exec(ctx, `
				UPDATE persona_relationships
				SET lower_persona_id=$2, upper_persona_id=$3
				WHERE pair_id=$1`,
				realPair.ID, collidedLower, collidedUpper,
			); err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() {
				_, _ = pool.Exec(context.Background(), `
					UPDATE persona_relationships
					SET lower_persona_id=$2, upper_persona_id=$3
					WHERE pair_id=$1`,
					realPair.ID, realPair.LowerPersonaID, realPair.UpperPersonaID,
				)
			})
			if _, err := followWithEvidence(ctx, service, realSource, realTarget, "homepage", writeEvidence); err == nil {
				t.Fatal("write against a colliding digest must be refused")
			}
			if _, err := unfollowWithEvidence(ctx, service, realSource, realTarget, unsetEvidence); err == nil {
				t.Fatal("unfollow against a colliding digest must be refused")
			}
			if _, err := service.GetRelationship(ctx, realSource, realTarget); err == nil {
				t.Fatal("read against a colliding digest must be refused")
			}
		})

		t.Run("the database refuses a direction endpoint outside the pair", func(t *testing.T) {
			if _, err := pool.Exec(ctx, `
				INSERT INTO persona_relationship_directions (
					pair_id, source_persona_id, target_persona_id, following, blocked, updated_at
				) VALUES ($1,$2,$3,TRUE,FALSE,NOW())`,
				realPair.ID, realSource, "integrity-third-endpoint",
			); err == nil {
				t.Fatal("third endpoint direction must be refused by the database")
			}
			if _, err := pool.Exec(ctx, `
				INSERT INTO persona_relationship_directions (
					pair_id, source_persona_id, target_persona_id, following, blocked, updated_at
				) VALUES ($1,$2,$2,TRUE,FALSE,NOW())`,
				realPair.ID, realSource,
			); err == nil {
				t.Fatal("reflexive direction must be refused by the database")
			}
		})
	})
}

func relationshipOutboxCount(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	source string,
	target string,
) int {
	t.Helper()
	pair, err := relmodel.NewPair(source, target)
	if err != nil {
		t.Fatal(err)
	}
	var count int
	if err := pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM persona_relationship_outbox WHERE aggregate_id=$1`,
		pair.ID,
	).Scan(&count); err != nil {
		t.Fatal(err)
	}
	return count
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-006
func TestPersonaRelationshipApplicationWriteAndFinalizeHaveOneWinner(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		now := time.Date(2026, 9, 19, 0, 0, 0, 0, time.UTC)
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool).WithClock(func() time.Time { return now })
		signer, err := relationshippersistence.NewMutationBasisSigner("user-service.test", "test-key", []relationshippersistence.MutationBasisKey{{ID: "test-key", Material: []byte(strings.Repeat("k", 32))}})
		if err != nil {
			t.Fatal(err)
		}
		signer.WithClock(func() time.Time { return now })
		service := relationshipapp.NewPersonaRelationshipService(store, nil, nil, nil, relationshipapp.WithMutationBasis(signer, store))

		// Write wins: finalize after deadline reads the committed receipt.
		basis, version, _, err := service.IssueMutationBasis(ctx, "winner-write-source", "winner-write-target")
		if err != nil {
			t.Fatal(err)
		}
		evidence := relationshipapp.CommandEvidence{IdempotencyKey: "winner-write-key", MutationBasis: basis, ExpectedVersion: version}
		written, err := service.Follow(ctx, "winner-write-source", "winner-write-target", "homepage", evidence)
		if err != nil || written.Outcome != relmodel.OutcomeCommitted {
			t.Fatalf("written=%+v err=%v", written, err)
		}
		now = now.Add(73 * time.Hour)
		recovered, err := service.FinalizeExpiredCommand(ctx, "winner-write-source", "winner-write-target", relmodel.CommandFollow, evidence)
		if err != nil || recovered.Outcome != relmodel.OutcomeCommitted || !recovered.Replayed {
			t.Fatalf("write winner recovery=%+v err=%v", recovered, err)
		}

		// Finalize wins after the original deadline; the same original write can
		// no longer execute.
		now = time.Date(2026, 9, 19, 0, 0, 0, 0, time.UTC)
		basis, version, _, err = service.IssueMutationBasis(ctx, "winner-expire-source", "winner-expire-target")
		if err != nil {
			t.Fatal(err)
		}
		evidence = relationshipapp.CommandEvidence{IdempotencyKey: "winner-expire-key", MutationBasis: basis, ExpectedVersion: version}
		now = now.Add(73 * time.Hour)
		finalized, err := service.FinalizeExpiredCommand(ctx, "winner-expire-source", "winner-expire-target", relmodel.CommandFollow, evidence)
		if err != nil || finalized.Outcome != relmodel.OutcomeExpired {
			t.Fatalf("finalized=%+v err=%v", finalized, err)
		}
		if _, err := service.Follow(ctx, "winner-expire-source", "winner-expire-target", "homepage", evidence); err == nil {
			t.Fatal("expired winner allowed original write")
		}

		// Physical receipt deletion cannot resurrect the old command because the
		// signed acceptUntil remains expired.
		if _, err := pool.Exec(ctx, `DELETE FROM persona_relationship_command_receipts WHERE actor_persona_id=$1 AND idempotency_key=$2`, "winner-expire-source", "winner-expire-key"); err != nil {
			t.Fatal(err)
		}
		if _, err := service.Follow(ctx, "winner-expire-source", "winner-expire-target", "homepage", evidence); err == nil {
			t.Fatal("deleted receipt resurrected expired basis")
		}
		history, err := service.RecoverCommand(ctx, "winner-expire-source", "winner-expire-target", relmodel.CommandFollow, "winner-expire-key")
		if err != nil || history.Outcome != relmodel.CommandOutcome("history_unavailable") {
			t.Fatalf("history=%+v err=%v", history, err)
		}
	})
}
