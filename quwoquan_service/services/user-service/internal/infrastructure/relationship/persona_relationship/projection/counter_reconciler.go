package projection

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
)

type ReconcileBatchResult struct {
	NextOwnerID string
	Scanned     int
	Repaired    int
}

// CounterReconciler is the low-frequency repair path. It is intentionally
// detached from Follow/Unfollow/Block command latency and compares one bounded
// owner page against the authoritative relationship directions.
type CounterReconciler struct {
	pool  *pgxpool.Pool
	cache ProfileCacheInvalidator
}

func NewCounterReconciler(
	pool *pgxpool.Pool,
	cache ProfileCacheInvalidator,
) *CounterReconciler {
	if pool == nil {
		panic("persona relationship counter reconciler pool is required")
	}
	return &CounterReconciler{pool: pool, cache: cache}
}

func (r *CounterReconciler) ReconcileBatch(
	ctx context.Context,
	afterOwnerID string,
	limit int,
) (ReconcileBatchResult, error) {
	if r == nil || r.pool == nil {
		return ReconcileBatchResult{}, fmt.Errorf(
			"persona relationship counter reconciler is unavailable",
		)
	}
	if limit <= 0 || limit > 1000 {
		limit = 200
	}
	rows, err := r.pool.Query(ctx, `
		SELECT user_id
		FROM user_profiles
		WHERE user_id > $1
		ORDER BY user_id
		LIMIT $2`,
		strings.TrimSpace(afterOwnerID),
		limit,
	)
	if err != nil {
		return ReconcileBatchResult{}, fmt.Errorf(
			"list relationship counter owners: %w",
			err,
		)
	}
	ownerIDs := make([]string, 0, limit)
	for rows.Next() {
		var ownerID string
		if err := rows.Scan(&ownerID); err != nil {
			rows.Close()
			return ReconcileBatchResult{}, fmt.Errorf(
				"scan relationship counter owner: %w",
				err,
			)
		}
		ownerIDs = append(ownerIDs, ownerID)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return ReconcileBatchResult{}, fmt.Errorf(
			"iterate relationship counter owners: %w",
			err,
		)
	}
	result := ReconcileBatchResult{Scanned: len(ownerIDs)}
	if len(ownerIDs) == 0 {
		return result, nil
	}
	result.NextOwnerID = ownerIDs[len(ownerIDs)-1]

	repairedRows, err := r.pool.Query(ctx, `
		WITH selected_owners AS (
			SELECT unnest($1::text[]) AS owner_id
		),
		active_personas AS (
			SELECT selected.owner_id, personas.sub_account_id AS persona_id
			FROM selected_owners AS selected
			JOIN personas ON personas.user_id = selected.owner_id
				AND personas.status <> 'retired'
		),
		fallback_personas AS (
			SELECT selected.owner_id, selected.owner_id AS persona_id
			FROM selected_owners AS selected
			WHERE NOT EXISTS (
				SELECT 1
				FROM active_personas
				WHERE active_personas.owner_id = selected.owner_id
			)
		),
		owner_personas AS (
			SELECT owner_id, persona_id FROM active_personas
			UNION ALL
			SELECT owner_id, persona_id FROM fallback_personas
		),
		follower_counts AS (
			SELECT owner_personas.owner_id, COUNT(direction.pair_id)::BIGINT AS value
			FROM owner_personas
			LEFT JOIN persona_relationship_directions AS direction
				ON direction.target_persona_id = owner_personas.persona_id
				AND direction.following = TRUE
			GROUP BY owner_personas.owner_id
		),
		following_counts AS (
			SELECT owner_personas.owner_id, COUNT(direction.pair_id)::BIGINT AS value
			FROM owner_personas
			LEFT JOIN persona_relationship_directions AS direction
				ON direction.source_persona_id = owner_personas.persona_id
				AND direction.following = TRUE
			GROUP BY owner_personas.owner_id
		),
		expected AS (
			SELECT selected.owner_id,
				COALESCE(follower_counts.value, 0) AS follower_count,
				COALESCE(following_counts.value, 0) AS following_count
			FROM selected_owners AS selected
			LEFT JOIN follower_counts USING (owner_id)
			LEFT JOIN following_counts USING (owner_id)
		)
		UPDATE user_profiles AS profile
		SET follower_count = expected.follower_count,
			following_count = expected.following_count,
			updated_at = NOW()
		FROM expected
		WHERE profile.user_id = expected.owner_id
			AND (
				profile.follower_count <> expected.follower_count
				OR profile.following_count <> expected.following_count
			)
		RETURNING profile.user_id`,
		ownerIDs,
	)
	if err != nil {
		return ReconcileBatchResult{}, fmt.Errorf(
			"reconcile relationship counters: %w",
			err,
		)
	}
	repairedOwnerIDs := make([]string, 0)
	for repairedRows.Next() {
		var ownerID string
		if err := repairedRows.Scan(&ownerID); err != nil {
			repairedRows.Close()
			return ReconcileBatchResult{}, fmt.Errorf(
				"scan repaired relationship counter: %w",
				err,
			)
		}
		repairedOwnerIDs = append(repairedOwnerIDs, ownerID)
	}
	repairedRows.Close()
	if err := repairedRows.Err(); err != nil {
		return ReconcileBatchResult{}, fmt.Errorf(
			"iterate repaired relationship counters: %w",
			err,
		)
	}
	result.Repaired = len(repairedOwnerIDs)
	for _, ownerID := range repairedOwnerIDs {
		reltelemetry.Collector().RecordCounterMismatch()
		if r.cache != nil {
			if err := r.cache.Del(ctx, ownerID); err != nil {
				return result, fmt.Errorf(
					"invalidate reconciled relationship counter cache for %s: %w",
					ownerID,
					err,
				)
			}
		}
	}
	return result, nil
}

func (r *CounterReconciler) ReconcileAll(
	ctx context.Context,
	batchSize int,
) (int, error) {
	cursor := ""
	repaired := 0
	for {
		result, err := r.ReconcileBatch(ctx, cursor, batchSize)
		if err != nil {
			return repaired, err
		}
		repaired += result.Repaired
		if result.Scanned == 0 || result.Scanned < normalizedBatchSize(batchSize) {
			return repaired, nil
		}
		if result.NextOwnerID == "" || result.NextOwnerID == cursor {
			return repaired, fmt.Errorf(
				"relationship counter reconciler cursor did not advance",
			)
		}
		cursor = result.NextOwnerID
	}
}

func (r *CounterReconciler) Run(
	ctx context.Context,
	interval time.Duration,
	batchSize int,
) error {
	if interval <= 0 {
		interval = 10 * time.Minute
	}
	batchSize = normalizedBatchSize(batchSize)
	cursor := ""
	for {
		result, err := r.ReconcileBatch(ctx, cursor, batchSize)
		if err != nil && ctx.Err() == nil {
			slog.ErrorContext(
				ctx,
				"persona relationship counter reconciliation failed",
				"err",
				err,
			)
		} else if err == nil {
			if result.Scanned < batchSize {
				cursor = ""
			} else {
				cursor = result.NextOwnerID
			}
		}
		timer := time.NewTimer(interval)
		select {
		case <-ctx.Done():
			if !timer.Stop() {
				<-timer.C
			}
			return nil
		case <-timer.C:
		}
	}
}

func normalizedBatchSize(value int) int {
	if value <= 0 || value > 1000 {
		return 200
	}
	return value
}
