// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-007
package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestPersonaFollowQuotaIsDecidedInsideTheCommandTransaction(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)

		t.Run("N-1 slots left admits exactly one of many concurrent targets", func(t *testing.T) {
			const (
				source    = "quota-race-source"
				slotLimit = 3
				targetFan = 20
			)
			setActivatedFollowLimit(t, ctx, pool, slotLimit)
			// 先占满 N-1 个名额，只留一个。
			for index := 0; index < slotLimit-1; index++ {
				target := fmt.Sprintf("quota-race-seed-%d", index)
				if _, err := followRelationship(t, ctx, service, source, target, "homepage", fmt.Sprintf("quota-race-seed-key-%d", index)); err != nil {
					t.Fatalf("seed follow %d: %v", index, err)
				}
			}

			type outcome struct {
				target string
				err    error
			}
			start := make(chan struct{})
			outcomes := make(chan outcome, targetFan)
			for index := 0; index < targetFan; index++ {
				target := fmt.Sprintf("quota-race-target-%d", index)
				key := fmt.Sprintf("quota-race-key-%d", index)
				go func() {
					<-start
					_, err := followRelationship(t, ctx, service, source, target, "homepage", key)
					outcomes <- outcome{target: target, err: err}
				}()
			}
			close(start)

			admitted := 0
			for index := 0; index < targetFan; index++ {
				got := <-outcomes
				if got.err == nil {
					admitted++
					continue
				}
				if !isFollowingLimitFailure(got.err) {
					t.Fatalf("concurrent follow of %s failed with %v, want quota rejection", got.target, got.err)
				}
			}
			if admitted != 1 {
				t.Fatalf("admitted %d concurrent follows, want exactly 1 remaining slot", admitted)
			}

			// 精确名额与权威出边一致，且超额请求没有留下任何成功事实。
			quota := readFollowQuota(t, ctx, pool, source)
			authoritative := countAuthoritativeFollowing(t, ctx, pool, source)
			if quota != slotLimit || authoritative != slotLimit {
				t.Fatalf("quota=%d authoritative=%d, want %d", quota, authoritative, slotLimit)
			}
			var events int
			if err := pool.QueryRow(ctx, `
				SELECT COUNT(*) FROM persona_relationship_outbox AS outbox
				JOIN persona_relationship_directions AS direction
				  ON direction.pair_id = outbox.aggregate_id
				WHERE direction.source_persona_id = $1 AND direction.following = TRUE`,
				source,
			).Scan(&events); err != nil {
				t.Fatal(err)
			}
			if events != slotLimit {
				t.Fatalf("business events=%d, want %d", events, slotLimit)
			}
		})

		t.Run("unfollow releases a slot and the reopened slot is reusable", func(t *testing.T) {
			const (
				source    = "quota-release-source"
				slotLimit = 2
			)
			setActivatedFollowLimit(t, ctx, pool, slotLimit)
			for index := 0; index < slotLimit; index++ {
				if _, err := followRelationship(t, ctx, service, source, fmt.Sprintf("quota-release-target-%d", index), "homepage", fmt.Sprintf("quota-release-key-%d", index)); err != nil {
					t.Fatal(err)
				}
			}
			if _, err := followRelationship(t, ctx, service, source, "quota-release-overflow", "homepage", "quota-release-overflow-key"); !isFollowingLimitFailure(err) {
				t.Fatalf("follow beyond the limit err=%v, want quota rejection", err)
			}
			if _, err := unfollowRelationship(t, ctx, service, source, "quota-release-target-0", "quota-release-unfollow-key"); err != nil {
				t.Fatal(err)
			}
			if readFollowQuota(t, ctx, pool, source) != slotLimit-1 {
				t.Fatal("unfollow must release exactly one slot")
			}
			if _, err := followRelationship(t, ctx, service, source, "quota-release-reused", "homepage", "quota-release-reused-key"); err != nil {
				t.Fatalf("released slot must be reusable, got %v", err)
			}
			if got := readFollowQuota(t, ctx, pool, source); got != slotLimit {
				t.Fatalf("quota=%d after reuse, want %d", got, slotLimit)
			}
		})

		t.Run("lowering the activated limit keeps existing edges and only refuses new ones", func(t *testing.T) {
			const source = "quota-downgrade-source"
			setActivatedFollowLimit(t, ctx, pool, 3)
			for index := 0; index < 3; index++ {
				if _, err := followRelationship(t, ctx, service, source, fmt.Sprintf("quota-downgrade-target-%d", index), "homepage", fmt.Sprintf("quota-downgrade-key-%d", index)); err != nil {
					t.Fatal(err)
				}
			}
			setActivatedFollowLimit(t, ctx, pool, 1)

			if countAuthoritativeFollowing(t, ctx, pool, source) != 3 {
				t.Fatal("lowering the limit must not delete existing relationships")
			}
			if _, err := followRelationship(t, ctx, service, source, "quota-downgrade-new", "homepage", "quota-downgrade-new-key"); !isFollowingLimitFailure(err) {
				t.Fatalf("over-quota persona must be refused new follows, got %v", err)
			}
			// 超额者仍可取关，并且原键回放不改变结果。
			evidence := relationshipEvidence(t, ctx, service, source, "quota-downgrade-target-0", "quota-downgrade-unfollow-key", relmodel.CommandUnfollow)
			if _, err := unfollowWithEvidence(ctx, service, source, "quota-downgrade-target-0", evidence); err != nil {
				t.Fatalf("over-quota persona must still be able to unfollow: %v", err)
			}
			replay, err := unfollowWithEvidence(ctx, service, source, "quota-downgrade-target-0", evidence)
			if err != nil || !replay.IdempotentReplay {
				t.Fatalf("replayed unfollow result=%+v err=%v", replay, err)
			}
			if readFollowQuota(t, ctx, pool, source) != 2 {
				t.Fatal("replayed unfollow must not release a second slot")
			}
		})

		t.Run("a blocked pair releases only the actor's own slot", func(t *testing.T) {
			const (
				actor = "quota-block-actor"
				peer  = "quota-block-peer"
			)
			setActivatedFollowLimit(t, ctx, pool, 10)
			if _, err := followRelationship(t, ctx, service, actor, peer, "homepage", "quota-block-actor-follow"); err != nil {
				t.Fatal(err)
			}
			if _, err := followRelationship(t, ctx, service, peer, actor, "homepage", "quota-block-peer-follow"); err != nil {
				t.Fatal(err)
			}
			if _, err := blockRelationship(t, ctx, service, actor, peer, "quota-block-key"); err != nil {
				t.Fatal(err)
			}
			if got := readFollowQuota(t, ctx, pool, actor); got != 0 {
				t.Fatalf("actor quota=%d after block, want 0", got)
			}
			if got := readFollowQuota(t, ctx, pool, peer); got != 0 {
				t.Fatalf("peer quota=%d after block, want 0", got)
			}
			// Block 清除双向 follow 时在同一事务按 source 排序释放双方名额。
			if got := countAuthoritativeFollowing(t, ctx, pool, peer); got != 0 {
				t.Fatalf("peer authoritative following=%d after block, want 0", got)
			}
		})

		t.Run("missing policy activation refuses new admissions", func(t *testing.T) {
			if _, err := pool.Exec(ctx,
				`DELETE FROM relationship_policy_activation WHERE policy_id='persona_following'`,
			); err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { setActivatedFollowLimit(t, context.Background(), pool, 1000) })
			if _, err := followRelationship(t, ctx, service, "quota-no-policy-source", "quota-no-policy-target", "homepage", "quota-no-policy-key"); err == nil {
				t.Fatal("missing policy activation must refuse new admissions instead of using a default")
			}
		})
	})
}

// setActivatedFollowLimit 以排他更新切换生效 revision，模拟受管配置激活。
func setActivatedFollowLimit(t *testing.T, ctx context.Context, pool *pgxpool.Pool, limit int) {
	t.Helper()
	var current int64
	if err := pool.QueryRow(ctx, `SELECT COALESCE(MAX(revision),0) FROM relationship_policy_activation WHERE policy_id='persona_following'`).Scan(&current); err != nil {
		t.Fatal(err)
	}
	revision := current + 1
	digest := sha256.Sum256([]byte(fmt.Sprintf("persona_following\x1f%d\x1f%d", revision, limit)))
	store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
	if err := store.ActivateFollowPolicy(ctx, relationshippersistence.FollowPolicyActivation{Revision: revision, MaxFollowingPerPersona: limit, ConfigDigest: hex.EncodeToString(digest[:])}); err != nil {
		t.Fatalf("activate follow limit %d: %v", limit, err)
	}
}

func readFollowQuota(t *testing.T, ctx context.Context, pool *pgxpool.Pool, sourcePersonaID string) int {
	t.Helper()
	var count int
	if err := pool.QueryRow(ctx,
		`SELECT COALESCE(
			(SELECT following_count FROM persona_follow_quota WHERE source_persona_id=$1), 0)`,
		sourcePersonaID,
	).Scan(&count); err != nil {
		t.Fatal(err)
	}
	return count
}

func countAuthoritativeFollowing(t *testing.T, ctx context.Context, pool *pgxpool.Pool, sourcePersonaID string) int {
	t.Helper()
	var count int
	if err := pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM persona_relationship_directions
		 WHERE source_persona_id=$1 AND following=TRUE`,
		sourcePersonaID,
	).Scan(&count); err != nil {
		t.Fatal(err)
	}
	return count
}

func isFollowingLimitFailure(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, relmodel.ErrFollowingLimitExceeded) {
		return true
	}
	// 服务层把它映射为 canonical failure；此处按 code 文本判定。
	return strings.Contains(err.Error(), "following_limit_exceeded")
}

func TestFollowPolicyActivationWaitsForInflightRevisionAndKeepsOldOnFailure(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		setActivatedFollowLimit(t, ctx, pool, 3)
		tx, err := pool.Begin(ctx)
		if err != nil {
			t.Fatal(err)
		}
		defer tx.Rollback(ctx)
		var oldRevision int64
		if err := tx.QueryRow(ctx, `SELECT revision FROM relationship_policy_activation WHERE policy_id='persona_following' FOR SHARE`).Scan(&oldRevision); err != nil {
			t.Fatal(err)
		}
		nextRevision := oldRevision + 1
		sum := sha256.Sum256([]byte(fmt.Sprintf("persona_following\x1f%d\x1f%d", nextRevision, 1)))
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		done := make(chan error, 1)
		go func() {
			done <- store.ActivateFollowPolicy(context.Background(), relationshippersistence.FollowPolicyActivation{Revision: nextRevision, MaxFollowingPerPersona: 1, ConfigDigest: hex.EncodeToString(sum[:])})
		}()
		select {
		case err := <-done:
			t.Fatalf("activation overtook inflight policy reader: %v", err)
		case <-time.After(150 * time.Millisecond):
		}
		if err := tx.Commit(ctx); err != nil {
			t.Fatal(err)
		}
		if err := <-done; err != nil {
			t.Fatal(err)
		}
		var limit int
		if err := pool.QueryRow(ctx, `SELECT max_following_per_persona FROM relationship_policy_activation WHERE policy_id='persona_following'`).Scan(&limit); err != nil || limit != 1 {
			t.Fatalf("limit=%d err=%v", limit, err)
		}
		if err := store.ActivateFollowPolicy(ctx, relationshippersistence.FollowPolicyActivation{Revision: nextRevision + 1, MaxFollowingPerPersona: 9, ConfigDigest: "wrong"}); err == nil {
			t.Fatal("bad digest activated")
		}
		if err := pool.QueryRow(ctx, `SELECT max_following_per_persona FROM relationship_policy_activation WHERE policy_id='persona_following'`).Scan(&limit); err != nil || limit != 1 {
			t.Fatalf("failed activation changed limit=%d err=%v", limit, err)
		}
	})
}

func TestFollowPolicyActivationSupportsContractLimits(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		for _, limit := range []int{3, 1000, 10000} {
			setActivatedFollowLimit(t, ctx, pool, limit)
			var got int
			if err := pool.QueryRow(ctx, `SELECT max_following_per_persona FROM relationship_policy_activation WHERE policy_id='persona_following'`).Scan(&got); err != nil || got != limit {
				t.Fatalf("activated limit=%d got=%d err=%v", limit, got, err)
			}
		}
	})
}
