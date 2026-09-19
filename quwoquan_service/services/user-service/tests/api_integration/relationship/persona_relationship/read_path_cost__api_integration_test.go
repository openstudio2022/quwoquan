// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-002
package api_integration

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestRelationshipPageReadsUseOneBatchRegardlessOfPageSize(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := relationshippersistence.NewPgPersonaRelationshipStore(pool)
		service := relationshipServiceForTest(t, store)

		const viewer = "read-cost-viewer"
		setActivatedFollowLimit(t, ctx, pool, 500)
		targets := make([]string, 0, 100)
		for index := 0; index < 100; index++ {
			target := fmt.Sprintf("read-cost-target-%03d", index)
			targets = append(targets, target)
			if err := usersupport.SeedAccountPersona(ctx, pool, "read-cost-owner-"+target, target); err != nil {
				t.Fatalf("seed public persona %d: %v", index, err)
			}
			if _, err := followRelationship(t, ctx, service, viewer, target, "homepage", fmt.Sprintf("read-cost-key-%03d", index)); err != nil {
				t.Fatalf("seed follow %d: %v", index, err)
			}
		}

		t.Run("one batch returns every relationship in the page", func(t *testing.T) {
			for _, pageSize := range []int{20, 100} {
				page := targets[:pageSize]
				states, err := service.GetRelationships(ctx, viewer, page)
				if err != nil {
					t.Fatalf("GetRelationships(%d) error = %v", pageSize, err)
				}
				if len(states) != pageSize {
					t.Fatalf("page size %d returned %d relationships", pageSize, len(states))
				}
				for _, target := range page {
					state, ok := states[target]
					if !ok || !state.IsFollowing {
						t.Fatalf("batch missing following state for %q: %+v", target, state)
					}
				}
			}
		})

		t.Run("batch and single read agree on the same snapshot", func(t *testing.T) {
			blocked := targets[0]
			if _, err := blockRelationship(t, ctx, service, viewer, blocked, "read-cost-block"); err != nil {
				t.Fatal(err)
			}
			states, err := service.GetRelationships(ctx, viewer, targets[:5])
			if err != nil {
				t.Fatal(err)
			}
			single, err := service.GetRelationship(ctx, viewer, blocked)
			if err != nil {
				t.Fatal(err)
			}
			batch := states[blocked]
			if batch.IsBlocked != single.IsBlocked ||
				batch.IsFollowing != single.IsFollowing ||
				batch.Version != single.Version {
				t.Fatalf("batch=%+v single=%+v must agree", batch, single)
			}
			if !batch.IsBlocked {
				t.Fatal("blocked relationship must be visible to the page filter")
			}
		})

		t.Run("unknown and self targets return a zero state instead of failing", func(t *testing.T) {
			states, err := service.GetRelationships(ctx, viewer, []string{
				"read-cost-unknown", viewer, "  ",
			})
			if err != nil {
				t.Fatal(err)
			}
			if state, ok := states["read-cost-unknown"]; !ok || state.IsFollowing || state.IsBlocked {
				t.Fatalf("unknown target state=%+v", state)
			}
			if _, ok := states[viewer]; ok {
				t.Fatal("self target must not appear in a relationship page")
			}
		})

		t.Run("paged reads hit the partial covering index", func(t *testing.T) {
			plan := explainFollowingPage(t, ctx, pool, viewer)
			if !strings.Contains(plan, "idx_persona_relationship_following_page") {
				t.Fatalf("following page did not use the covering index:\n%s", plan)
			}
			if strings.Contains(plan, "Seq Scan on persona_relationship_directions") {
				t.Fatalf("following page fell back to a sequential scan:\n%s", plan)
			}
			// 覆盖索引已按游标二元组预排序，分页不应再排序一次。
			if strings.Contains(plan, "Sort") {
				t.Fatalf("cursor ordering still needs a sort step:\n%s", plan)
			}
			// 被取代的旧索引必须退役，避免同一访问路径上并存两套索引。
			for _, retired := range []string{
				"idx_persona_relationship_following\n",
				"idx_persona_relationship_followers\n",
				"idx_persona_relationship_blocked\n",
			} {
				if strings.Contains(plan, strings.TrimSuffix(retired, "\n")+" ") {
					t.Fatalf("retired index %q is still present:\n%s", retired, plan)
				}
			}
		})

		t.Run("short terminal search page has no cursor", func(t *testing.T) {
			items, next, err := service.ListFollowing(ctx, viewer, "", 20, viewer, "target-099")
			if err != nil {
				t.Fatal(err)
			}
			if len(items) != 1 || next != "" {
				t.Fatalf("terminal short page items=%d next=%q", len(items), next)
			}
		})

		t.Run("cursor rejects tamper and cross-query reuse", func(t *testing.T) {
			_, cursor, err := service.ListFollowing(ctx, viewer, "", 10, viewer, "target")
			if err != nil || cursor == "" {
				t.Fatalf("first searched page cursor=%q err=%v", cursor, err)
			}
			replacement := "A"
			if cursor[len(cursor)-1:] == replacement {
				replacement = "B"
			}
			tampered := cursor[:len(cursor)-1] + replacement
			if _, _, err := service.ListFollowing(ctx, viewer, tampered, 10, viewer, "target"); err == nil {
				t.Fatal("tampered cursor must be rejected")
			}
			if _, _, err := service.ListFollowing(ctx, viewer, cursor, 10, viewer, "different"); err == nil {
				t.Fatal("cursor must not be reusable under another query")
			}
			if _, _, err := service.ListFollowing(ctx, "another-owner", cursor, 10, viewer, "target"); err == nil {
				t.Fatal("cursor must not be reusable for another owner")
			}
		})

		t.Run("same timestamp keyset has no repeats or holes", func(t *testing.T) {
			if _, err := pool.Exec(ctx, `UPDATE persona_relationship_directions SET followed_at=$1 WHERE source_persona_id=$2 AND following=TRUE`, time.Date(2026, 9, 19, 1, 2, 3, 0, time.UTC), viewer); err != nil {
				t.Fatal(err)
			}
			seen := map[string]struct{}{}
			cursor := ""
			for page := 0; page < 20; page++ {
				items, next, err := service.ListFollowing(ctx, viewer, cursor, 7, viewer, "")
				if err != nil {
					t.Fatal(err)
				}
				for _, item := range items {
					if _, duplicate := seen[item.TargetPersonaID]; duplicate {
						t.Fatalf("same-timestamp pagination repeated %q", item.TargetPersonaID)
					}
					seen[item.TargetPersonaID] = struct{}{}
				}
				if next == "" {
					break
				}
				cursor = next
			}
			if len(seen) != len(targets)-1 {
				t.Fatalf("same-timestamp pagination saw %d of %d", len(seen), len(targets)-1)
			}
		})

		t.Run("stable cursor pages the whole set without repeats or holes", func(t *testing.T) {
			seen := make(map[string]struct{}, len(targets))
			cursor := ""
			for page := 0; page < 20; page++ {
				items, next, err := service.ListFollowing(ctx, viewer, cursor, 10, viewer, "")
				if err != nil {
					t.Fatal(err)
				}
				for _, item := range items {
					if _, duplicate := seen[item.TargetPersonaID]; duplicate {
						t.Fatalf("cursor paging repeated %q", item.TargetPersonaID)
					}
					seen[item.TargetPersonaID] = struct{}{}
				}
				if strings.TrimSpace(next) == "" {
					break
				}
				cursor = next
			}
			// 第一个目标已在上一子测试里被 block 清边，因此不在关注集合内。
			if len(seen) != len(targets)-1 {
				t.Fatalf("cursor paging saw %d of %d following edges", len(seen), len(targets)-1)
			}
		})
	})
}

// explainFollowingPage 用真实执行计划证明分页读命中 partial covering 索引，
// 而不是以返回条数上限冒充有界扫描。
func explainFollowingPage(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	sourcePersonaID string,
) string {
	t.Helper()
	if _, err := pool.Exec(ctx, `ANALYZE persona_relationship_directions`); err != nil {
		t.Fatal(err)
	}
	// 关闭顺序扫描偏好，使计划器在小表上也暴露真实可用索引；索引缺失时
	// 计划里仍会出现 Seq Scan，因此该断言不会被此设置掩盖。
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `SET LOCAL enable_seqscan = off`); err != nil {
		t.Fatal(err)
	}
	rows, err := tx.Query(ctx, `
		EXPLAIN (ANALYZE, BUFFERS)
		SELECT pair_id, source_persona_id, target_persona_id, following, blocked,
			follow_source, followed_at, blocked_at, updated_at
		FROM persona_relationship_directions
		WHERE source_persona_id = $1 AND following = TRUE
		ORDER BY followed_at DESC, pair_id DESC
		LIMIT 21`, sourcePersonaID)
	if err != nil {
		t.Fatalf("explain following page: %v", err)
	}
	defer rows.Close()
	var plan strings.Builder
	for rows.Next() {
		var line string
		if err := rows.Scan(&line); err != nil {
			t.Fatal(err)
		}
		plan.WriteString(line)
		plan.WriteString("\n")
	}
	if err := rows.Err(); err != nil {
		t.Fatal(err)
	}
	return plan.String()
}
