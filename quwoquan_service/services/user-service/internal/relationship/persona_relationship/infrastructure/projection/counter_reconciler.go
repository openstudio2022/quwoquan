package projection

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type ReconcileBatchResult struct {
	NextPersonaID string
	Scanned       int
	Repaired      int
	Generation    string
}

// CounterReconciler rebuilds a shadow contribution generation from a fixed
// authority snapshot, verifies it against the live member ledger, and only
// then publishes the repaired live buckets. It is never used by commands or
// normal event projection and performs no edge COUNT query.
type CounterReconciler struct {
	pool        *pgxpool.Pool
	bucketCount int
}

func NewCounterReconciler(pool *pgxpool.Pool, _ ProfileCacheInvalidator) *CounterReconciler {
	if pool == nil {
		panic("persona relationship counter reconciler pool is required")
	}
	return &CounterReconciler{pool: pool, bucketCount: DefaultRelationshipStatisticsBuckets}
}

func (r *CounterReconciler) ReconcileBatch(ctx context.Context, afterPersonaID string, limit int) (ReconcileBatchResult, error) {
	if r == nil || r.pool == nil {
		return ReconcileBatchResult{}, errors.New("persona relationship counter reconciler is unavailable")
	}
	limit = normalizedBatchSize(limit)
	generation := uuid.NewString()
	tx, err := r.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead})
	if err != nil {
		return ReconcileBatchResult{}, fmt.Errorf("begin relationship statistics repair: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()
	rows, err := tx.Query(ctx, `
		SELECT DISTINCT persona_id
		FROM persona_relationship_statistics_members
		WHERE persona_id > $1
		ORDER BY persona_id
		LIMIT $2`, strings.TrimSpace(afterPersonaID), limit)
	if err != nil {
		return ReconcileBatchResult{}, fmt.Errorf("list relationship repair personas: %w", err)
	}
	personaIDs := make([]string, 0, limit)
	for rows.Next() {
		var personaID string
		if err := rows.Scan(&personaID); err != nil {
			rows.Close()
			return ReconcileBatchResult{}, err
		}
		personaIDs = append(personaIDs, personaID)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return ReconcileBatchResult{}, err
	}
	result := ReconcileBatchResult{Scanned: len(personaIDs), Generation: generation}
	if len(personaIDs) == 0 {
		if err := tx.Commit(ctx); err != nil {
			return result, err
		}
		committed = true
		return result, nil
	}
	result.NextPersonaID = personaIDs[len(personaIDs)-1]
	if _, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_statistics_buckets (
			generation, persona_id, contribution_kind, bucket, value,
			max_source_version, updated_at
		)
		SELECT $1, persona_id, contribution_kind, bucket,
			SUM(current_contribution), MAX(last_applied_version), NOW()
		FROM persona_relationship_statistics_members
		WHERE persona_id = ANY($2::text[])
		GROUP BY persona_id, contribution_kind, bucket`, generation, personaIDs); err != nil {
		return result, fmt.Errorf("build relationship repair generation: %w", err)
	}
	mismatchRows, err := tx.Query(ctx, `
		WITH expected AS (
			SELECT persona_id, contribution_kind, bucket, value
			FROM persona_relationship_statistics_buckets
			WHERE generation=$1
		), live AS (
			SELECT persona_id, contribution_kind, bucket, value
			FROM persona_relationship_statistics_buckets
			WHERE generation='live' AND persona_id = ANY($2::text[])
		)
		SELECT COALESCE(expected.persona_id, live.persona_id)
		FROM expected FULL OUTER JOIN live USING (persona_id, contribution_kind, bucket)
		WHERE COALESCE(expected.value, 0) <> COALESCE(live.value, 0)`, generation, personaIDs)
	if err != nil {
		return result, fmt.Errorf("verify relationship repair generation: %w", err)
	}
	mismatches := 0
	for mismatchRows.Next() {
		var personaID string
		if err := mismatchRows.Scan(&personaID); err != nil {
			mismatchRows.Close()
			return result, err
		}
		mismatches++
	}
	mismatchRows.Close()
	if err := mismatchRows.Err(); err != nil {
		return result, err
	}
	if mismatches > 0 {
		if _, err := tx.Exec(ctx, `
			DELETE FROM persona_relationship_statistics_buckets
			WHERE generation='live' AND persona_id = ANY($1::text[])`, personaIDs); err != nil {
			return result, err
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO persona_relationship_statistics_buckets (
				generation, persona_id, contribution_kind, bucket, value,
				max_source_version, updated_at
			)
			SELECT 'live', persona_id, contribution_kind, bucket, value,
				max_source_version, NOW()
			FROM persona_relationship_statistics_buckets
			WHERE generation=$1`, generation); err != nil {
			return result, err
		}
		result.Repaired = mismatches
	}
	if _, err := tx.Exec(ctx, `DELETE FROM persona_relationship_statistics_buckets WHERE generation=$1`, generation); err != nil {
		return result, err
	}
	if err := tx.Commit(ctx); err != nil {
		return result, fmt.Errorf("commit relationship statistics repair: %w", err)
	}
	committed = true
	return result, nil
}

func (r *CounterReconciler) Run(ctx context.Context, interval time.Duration, batchSize int) error {
	if interval <= 0 {
		interval = 10 * time.Minute
	}
	cursor := ""
	for {
		result, err := r.ReconcileBatch(ctx, cursor, batchSize)
		if err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "persona relationship statistics repair failed", "err", err)
		} else if err == nil {
			if result.Scanned < normalizedBatchSize(batchSize) {
				cursor = ""
			} else {
				cursor = result.NextPersonaID
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
