package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("experiment assignment postgres pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (store *PostgresStore) EnsureSchema(ctx context.Context) error {
	_, err := store.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS experiment_assignment_facts (
  id VARCHAR(36) PRIMARY KEY,
  experiment_id VARCHAR(64) NOT NULL REFERENCES experiments(id),
  subject_key VARCHAR(128) NOT NULL,
  variant VARCHAR(32) NOT NULL,
  experiment_revision BIGINT NOT NULL,
  assigned_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT uq_assignment_subject UNIQUE(experiment_id, experiment_revision, subject_key)
);
CREATE INDEX IF NOT EXISTS idx_assignment_experiment
  ON experiment_assignment_facts(experiment_id, variant);
CREATE INDEX IF NOT EXISTS idx_assignment_subject
  ON experiment_assignment_facts(subject_key);`)
	return err
}

func (store *PostgresStore) Append(
	ctx context.Context,
	fact assignmentdomain.Fact,
) (assignmentdomain.Fact, bool, error) {
	canonicalInput, err := assignmentdomain.NewFact(fact)
	if err != nil {
		return assignmentdomain.Fact{}, false, err
	}
	assignedAt, _ := time.Parse(time.RFC3339, canonicalInput.AssignedAt)
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return assignmentdomain.Fact{}, false, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var canonical assignmentdomain.Fact
	var canonicalAt time.Time
	err = tx.QueryRow(ctx, `
INSERT INTO experiment_assignment_facts(
  id, experiment_id, subject_key, variant, experiment_revision, assigned_at
) VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (experiment_id, experiment_revision, subject_key) DO NOTHING
RETURNING id, experiment_id, subject_key, variant, experiment_revision, assigned_at`,
		canonicalInput.ID,
		canonicalInput.ExperimentID,
		canonicalInput.SubjectKey,
		canonicalInput.Variant,
		canonicalInput.ExperimentRevision,
		assignedAt,
	).Scan(
		&canonical.ID,
		&canonical.ExperimentID,
		&canonical.SubjectKey,
		&canonical.Variant,
		&canonical.ExperimentRevision,
		&canonicalAt,
	)
	inserted := true
	if errors.Is(err, pgx.ErrNoRows) {
		inserted = false
		err = tx.QueryRow(ctx, `
SELECT id, experiment_id, subject_key, variant, experiment_revision, assigned_at
FROM experiment_assignment_facts
WHERE experiment_id=$1 AND experiment_revision=$2 AND subject_key=$3`,
			canonicalInput.ExperimentID,
			canonicalInput.ExperimentRevision,
			canonicalInput.SubjectKey,
		).Scan(
			&canonical.ID,
			&canonical.ExperimentID,
			&canonical.SubjectKey,
			&canonical.Variant,
			&canonical.ExperimentRevision,
			&canonicalAt,
		)
	}
	if err != nil {
		return assignmentdomain.Fact{}, false, err
	}
	canonical.AssignedAt = canonicalAt.UTC().Format(time.RFC3339)
	canonical, err = assignmentdomain.NewFact(canonical)
	if err != nil {
		return assignmentdomain.Fact{}, false, err
	}
	if !inserted && canonical.Variant != canonicalInput.Variant {
		return assignmentdomain.Fact{}, false, fmt.Errorf(
			"assignment identity conflicts with immutable variant",
		)
	}
	if err := tx.Commit(ctx); err != nil {
		return assignmentdomain.Fact{}, false, err
	}
	return canonical, inserted, nil
}

func (store *PostgresStore) Get(
	ctx context.Context,
	experimentID string,
	experimentRevision int64,
	subjectKey string,
) (assignmentdomain.Fact, error) {
	var fact assignmentdomain.Fact
	var assignedAt time.Time
	err := store.pool.QueryRow(ctx, `
SELECT id, experiment_id, subject_key, variant, experiment_revision, assigned_at
FROM experiment_assignment_facts
WHERE experiment_id=$1 AND experiment_revision=$2 AND subject_key=$3`,
		experimentID,
		experimentRevision,
		subjectKey,
	).Scan(
		&fact.ID,
		&fact.ExperimentID,
		&fact.SubjectKey,
		&fact.Variant,
		&fact.ExperimentRevision,
		&assignedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return assignmentdomain.Fact{}, assignmentdomain.ErrNotFound
	}
	if err != nil {
		return assignmentdomain.Fact{}, err
	}
	fact.AssignedAt = assignedAt.UTC().Format(time.RFC3339)
	return assignmentdomain.NewFact(fact)
}

func (store *PostgresStore) Stats(
	ctx context.Context,
	experimentID string,
	experimentRevision int64,
) (assignmentdomain.Stats, error) {
	rows, err := store.pool.Query(ctx, `
SELECT variant, COUNT(*) FROM experiment_assignment_facts
WHERE experiment_id=$1 AND experiment_revision=$2 GROUP BY variant ORDER BY variant`,
		experimentID,
		experimentRevision,
	)
	if err != nil {
		return assignmentdomain.Stats{}, err
	}
	defer rows.Close()
	stats := assignmentdomain.Stats{VariantCounts: map[string]int{}}
	for rows.Next() {
		var variant string
		var count int
		if err := rows.Scan(&variant, &count); err != nil {
			return assignmentdomain.Stats{}, err
		}
		stats.VariantCounts[variant] = count
		stats.AssignedSubjects += count
	}
	return stats, rows.Err()
}

var (
	_ assignmentapp.Sink   = (*PostgresStore)(nil)
	_ assignmentapp.Reader = (*PostgresStore)(nil)
)
