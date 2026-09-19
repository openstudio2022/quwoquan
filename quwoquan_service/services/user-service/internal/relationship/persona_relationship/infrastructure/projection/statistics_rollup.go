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

type StatisticsState string

const (
	StatisticsAvailable   StatisticsState = "available"
	StatisticsStale       StatisticsState = "stale"
	StatisticsUnavailable StatisticsState = "unavailable"
)

type PersonaStatisticsSnapshot struct {
	Generation       string
	StatsVersion     int64
	FollowerCount    int64
	FollowingCount   int64
	SourceCheckpoint string
	AsOf             time.Time
	ExpiresAt        time.Time
}

type PersonaStatisticsSlice struct {
	PersonaID string
	State     StatisticsState
	Snapshot  *PersonaStatisticsSnapshot
}

// StatisticsRollup publishes immutable generation rows from fixed buckets.
// It never updates user_profiles and therefore does not change profile edit
// timestamps when relationship statistics change.
type StatisticsRollup struct {
	pool     *pgxpool.Pool
	now      func() time.Time
	freshFor time.Duration
	staleFor time.Duration
}

func NewStatisticsRollup(pool *pgxpool.Pool) *StatisticsRollup {
	if pool == nil {
		panic("persona relationship statistics rollup pool is required")
	}
	return &StatisticsRollup{
		pool:     pool,
		now:      func() time.Time { return time.Now().UTC() },
		freshFor: 5 * time.Second,
		staleFor: time.Minute,
	}
}

func (r *StatisticsRollup) WithClock(now func() time.Time) *StatisticsRollup {
	if r != nil && now != nil {
		r.now = now
	}
	return r
}

func (r *StatisticsRollup) Rollup(ctx context.Context) (string, int, error) {
	if r == nil || r.pool == nil {
		return "", 0, errors.New("persona relationship statistics rollup is unavailable")
	}
	generation := uuid.NewString()
	now := r.now().UTC()
	tx, err := r.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead})
	if err != nil {
		return "", 0, fmt.Errorf("begin relationship statistics rollup: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()
	var checkpoint string
	if err := tx.QueryRow(ctx, `
		SELECT COALESCE(MAX(aggregate_version), 0)::text
		FROM persona_relationship_statistics_inbox`).Scan(&checkpoint); err != nil {
		return "", 0, fmt.Errorf("read relationship statistics checkpoint: %w", err)
	}
	command, err := tx.Exec(ctx, `
		WITH totals AS (
			SELECT persona_id,
				COALESCE(SUM(value) FILTER (WHERE contribution_kind='follower'), 0)::BIGINT AS follower_count,
				COALESCE(SUM(value) FILTER (WHERE contribution_kind='following'), 0)::BIGINT AS following_count,
				COALESCE(MAX(max_source_version), 0)::BIGINT AS stats_version
			FROM persona_relationship_statistics_buckets
			WHERE generation='live'
			GROUP BY persona_id
		)
		INSERT INTO persona_relationship_statistics_rollups (
			generation, persona_id, stats_version, follower_count,
			following_count, source_checkpoint, as_of, expires_at
		)
		SELECT $1, persona_id, stats_version, follower_count, following_count,
			$2, $3, $4
		FROM totals`, generation, checkpoint, now, now.Add(r.freshFor))
	if err != nil {
		return "", 0, fmt.Errorf("materialize relationship statistics rollup: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_statistics_reader_generation (
			id, generation, source_checkpoint, published_at
		) VALUES ('current', $1,$2,$3)
		ON CONFLICT (id) DO UPDATE SET
			generation=EXCLUDED.generation,
			source_checkpoint=EXCLUDED.source_checkpoint,
			published_at=EXCLUDED.published_at`, generation, checkpoint, now); err != nil {
		return "", 0, fmt.Errorf("publish relationship statistics generation: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return "", 0, fmt.Errorf("commit relationship statistics rollup: %w", err)
	}
	committed = true
	return generation, int(command.RowsAffected()), nil
}

func (r *StatisticsRollup) Read(ctx context.Context, personaID string) (PersonaStatisticsSlice, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return PersonaStatisticsSlice{}, errors.New("persona statistics id is required")
	}
	var snapshot PersonaStatisticsSnapshot
	err := r.pool.QueryRow(ctx, `
		SELECT rollup.generation, rollup.stats_version, rollup.follower_count,
			rollup.following_count, rollup.source_checkpoint, rollup.as_of,
			rollup.expires_at
		FROM persona_relationship_statistics_reader_generation AS reader
		JOIN persona_relationship_statistics_rollups AS rollup
			ON rollup.generation=reader.generation
		WHERE reader.id='current' AND rollup.persona_id=$1`, personaID).Scan(
		&snapshot.Generation, &snapshot.StatsVersion, &snapshot.FollowerCount,
		&snapshot.FollowingCount, &snapshot.SourceCheckpoint, &snapshot.AsOf,
		&snapshot.ExpiresAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return PersonaStatisticsSlice{PersonaID: personaID, State: StatisticsUnavailable}, nil
	}
	if err != nil {
		return PersonaStatisticsSlice{}, fmt.Errorf("read persona relationship statistics: %w", err)
	}
	now := r.now().UTC()
	state := StatisticsAvailable
	if now.After(snapshot.ExpiresAt) {
		state = StatisticsStale
	}
	if now.After(snapshot.AsOf.Add(r.staleFor)) {
		return PersonaStatisticsSlice{PersonaID: personaID, State: StatisticsUnavailable}, nil
	}
	return PersonaStatisticsSlice{PersonaID: personaID, State: state, Snapshot: &snapshot}, nil
}

func (r *StatisticsRollup) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, _, err := r.Rollup(ctx); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "persona relationship statistics rollup failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

// SwitchReaderGeneration performs the only rollback/cutover of statistics readers.
// A target below minCheckpoint is refused so rollback cannot discard facts that
// arrived after rehearsal/backfill.
func (r *StatisticsRollup) SwitchReaderGeneration(ctx context.Context, expectedCurrent, target, minCheckpoint string) error {
	tx, err := r.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var current string
	if err := tx.QueryRow(ctx, `SELECT generation FROM persona_relationship_statistics_reader_generation WHERE id='current' FOR UPDATE`).Scan(&current); err != nil {
		return err
	}
	if current != expectedCurrent {
		return errors.New("relationship statistics reader generation changed")
	}
	var checkpoint string
	if err := tx.QueryRow(ctx, `SELECT source_checkpoint FROM persona_relationship_statistics_rollups WHERE generation=$1 ORDER BY source_checkpoint DESC LIMIT 1`, target).Scan(&checkpoint); err != nil {
		return err
	}
	if compareCheckpoint(checkpoint, minCheckpoint) < 0 {
		return errors.New("relationship statistics rollback would lose newer facts")
	}
	if _, err := tx.Exec(ctx, `UPDATE persona_relationship_statistics_reader_generation SET generation=$1,source_checkpoint=$2,published_at=NOW() WHERE id='current'`, target, checkpoint); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func compareCheckpoint(left, right string) int {
	left = strings.TrimSpace(left)
	right = strings.TrimSpace(right)
	if len(left) < len(right) {
		return -1
	}
	if len(left) > len(right) {
		return 1
	}
	if left < right {
		return -1
	}
	if left > right {
		return 1
	}
	return 0
}
