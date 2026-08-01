package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("experiment postgres pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (s *PostgresStore) EnsureSchema(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS experiments (
  id VARCHAR(64) PRIMARY KEY,
  key VARCHAR(128) NOT NULL UNIQUE,
  version BIGINT NOT NULL,
  status VARCHAR(32) NOT NULL,
  variants JSONB NOT NULL,
  audience_rule JSONB NOT NULL,
  starts_at TIMESTAMPTZ NULL,
  ends_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE experiments DROP COLUMN IF EXISTS allocation_seed;
CREATE INDEX IF NOT EXISTS idx_experiments_status_window
  ON experiments(status, starts_at, ends_at);

CREATE TABLE IF NOT EXISTS experiment_policy_revisions (
  experiment_id VARCHAR(64) NOT NULL REFERENCES experiments(id),
  revision BIGINT NOT NULL,
  key VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  variants JSONB NOT NULL,
  audience_rule JSONB NOT NULL,
  starts_at TIMESTAMPTZ NULL,
  ends_at TIMESTAMPTZ NULL,
  activated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(experiment_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_experiment_policy_revisions_activated
  ON experiment_policy_revisions(experiment_id, activated_at);
INSERT INTO experiment_policy_revisions(
  experiment_id, revision, key, status, variants, audience_rule,
  starts_at, ends_at, activated_at
)
SELECT id, version, key, status, variants, audience_rule, starts_at, ends_at, updated_at
FROM experiments
ON CONFLICT (experiment_id, revision) DO NOTHING;

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
  ON experiment_assignment_facts(subject_key);

CREATE TABLE IF NOT EXISTS product_ops_outbox (
  event_id VARCHAR(128) PRIMARY KEY,
  event_type VARCHAR(128) NOT NULL,
  aggregate_type VARCHAR(128) NOT NULL,
  aggregate_id VARCHAR(128) NOT NULL,
  payload JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  dispatched_at TIMESTAMPTZ NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_error TEXT NOT NULL DEFAULT '',
  lease_owner VARCHAR(160) NULL,
  leased_until TIMESTAMPTZ NULL
);
ALTER TABLE product_ops_outbox ADD COLUMN IF NOT EXISTS lease_owner VARCHAR(160) NULL;
ALTER TABLE product_ops_outbox ADD COLUMN IF NOT EXISTS leased_until TIMESTAMPTZ NULL;
CREATE INDEX IF NOT EXISTS idx_product_ops_outbox_ready
  ON product_ops_outbox(dispatched_at, next_attempt_at, occurred_at);

CREATE TABLE IF NOT EXISTS experiment_idempotency_receipts (
	  experiment_id VARCHAR(64) NOT NULL,
	  idempotency_key VARCHAR(160) NOT NULL,
	  command_digest VARCHAR(64) NOT NULL,
	  version BIGINT NOT NULL,
	  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	  PRIMARY KEY(experiment_id, idempotency_key)
);
`)
	return err
}

func (s *PostgresStore) Load(ctx context.Context, id string) (model.Experiment, error) {
	row := s.pool.QueryRow(ctx, experimentSelect+` WHERE id=$1`, strings.TrimSpace(id))
	return scanExperiment(row)
}

func (s *PostgresStore) LoadRevision(
	ctx context.Context,
	id string,
	revision int64,
) (model.Experiment, error) {
	normalizedID := strings.TrimSpace(id)
	row := s.pool.QueryRow(ctx, `SELECT
  experiment_id, key, revision, status, variants, audience_rule,
  starts_at, ends_at, activated_at, activated_at
FROM experiment_policy_revisions
WHERE experiment_id=$1 AND revision=$2`, normalizedID, revision)
	experiment, err := scanExperiment(row)
	if !errors.Is(err, model.ErrNotFound) {
		return experiment, err
	}
	// Existing deployments and fixture-created current aggregates are readable
	// before their first activation backfill. Historical revisions never fall
	// through to the mutable current row.
	return scanExperiment(s.pool.QueryRow(
		ctx,
		experimentSelect+` WHERE id=$1 AND version=$2`,
		normalizedID,
		revision,
	))
}

func (s *PostgresStore) List(ctx context.Context) ([]model.Experiment, error) {
	rows, err := s.pool.Query(ctx, experimentSelect+` ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]model.Experiment, 0)
	for rows.Next() {
		experiment, err := scanExperiment(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, experiment)
	}
	return out, rows.Err()
}

func (s *PostgresStore) Replay(
	ctx context.Context,
	experimentID, idempotencyKey, commandDigest string,
) (ports.CommitReceipt, bool, error) {
	experimentID = strings.TrimSpace(experimentID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	commandDigest = strings.TrimSpace(commandDigest)
	if experimentID == "" || idempotencyKey == "" || commandDigest == "" {
		return ports.CommitReceipt{}, false, errors.New("experiment receipt lookup requires experiment, idempotency key and command digest")
	}
	var receipt ports.CommitReceipt
	var storedDigest string
	err := s.pool.QueryRow(ctx, `
SELECT experiment_id, version, command_digest FROM experiment_idempotency_receipts
WHERE experiment_id=$1 AND idempotency_key=$2`, experimentID, idempotencyKey).
		Scan(&receipt.ExperimentID, &receipt.Version, &storedDigest)
	if errors.Is(err, pgx.ErrNoRows) {
		return ports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return ports.CommitReceipt{}, false, err
	}
	if storedDigest != commandDigest {
		return ports.CommitReceipt{}, false, model.ErrIdempotencyConflict
	}
	receipt.Replayed = true
	return receipt, true, nil
}

func (s *PostgresStore) Commit(
	ctx context.Context,
	expectedVersion int64,
	changes ports.ChangeSet,
) (ports.CommitReceipt, error) {
	idempotencyKey := strings.TrimSpace(changes.IdempotencyKey)
	if idempotencyKey == "" {
		return ports.CommitReceipt{}, errors.New("experiment idempotency key is required")
	}
	if len(idempotencyKey) > 160 {
		return ports.CommitReceipt{}, errors.New("experiment idempotency key exceeds 160 bytes")
	}
	commandDigest := strings.TrimSpace(changes.CommandDigest)
	if commandDigest == "" {
		return ports.CommitReceipt{}, errors.New("experiment command digest is required")
	}
	if err := changes.Experiment.Validate(); err != nil {
		return ports.CommitReceipt{}, err
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var receipt ports.CommitReceipt
	var storedDigest string
	err = tx.QueryRow(ctx, `
SELECT experiment_id, version, command_digest FROM experiment_idempotency_receipts
WHERE experiment_id=$1 AND idempotency_key=$2`, changes.Experiment.ID, idempotencyKey).
		Scan(&receipt.ExperimentID, &receipt.Version, &storedDigest)
	if err == nil {
		if storedDigest != commandDigest {
			return ports.CommitReceipt{}, model.ErrIdempotencyConflict
		}
		receipt.Replayed = true
		return receipt, tx.Commit(ctx)
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return ports.CommitReceipt{}, err
	}

	variants, audience, startsAt, endsAt, createdAt, updatedAt, err := experimentColumns(changes.Experiment)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO experiment_policy_revisions(
  experiment_id, revision, key, status, variants, audience_rule,
  starts_at, ends_at, activated_at
)
SELECT id, version, key, status, variants, audience_rule, starts_at, ends_at, updated_at
FROM experiments WHERE id=$1 AND version=$2
ON CONFLICT (experiment_id, revision) DO NOTHING`, changes.Experiment.ID, expectedVersion); err != nil {
		return ports.CommitReceipt{}, err
	}
	commandTag, err := tx.Exec(ctx, `
UPDATE experiments SET
  key=$3, version=$4, status=$5, variants=$6, audience_rule=$7,
  starts_at=$8, ends_at=$9, created_at=$10, updated_at=$11
WHERE id=$1 AND version=$2`,
		changes.Experiment.ID, expectedVersion, changes.Experiment.Key, changes.Experiment.Version,
		changes.Experiment.Status, variants, audience,
		startsAt, endsAt, createdAt, updatedAt)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if commandTag.RowsAffected() != 1 {
		err = tx.QueryRow(ctx, `
SELECT experiment_id, version, command_digest FROM experiment_idempotency_receipts
WHERE experiment_id=$1 AND idempotency_key=$2`, changes.Experiment.ID, idempotencyKey).
			Scan(&receipt.ExperimentID, &receipt.Version, &storedDigest)
		if err == nil {
			if storedDigest != commandDigest {
				return ports.CommitReceipt{}, model.ErrIdempotencyConflict
			}
			receipt.Replayed = true
			return receipt, tx.Commit(ctx)
		}
		if !errors.Is(err, pgx.ErrNoRows) {
			return ports.CommitReceipt{}, err
		}
		return ports.CommitReceipt{}, model.ErrVersionConflict
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO experiment_policy_revisions(
  experiment_id, revision, key, status, variants, audience_rule,
  starts_at, ends_at, activated_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
		changes.Experiment.ID, changes.Experiment.Version, changes.Experiment.Key,
		changes.Experiment.Status, variants, audience, startsAt, endsAt, updatedAt,
	); err != nil {
		return ports.CommitReceipt{}, err
	}
	for _, event := range changes.Events {
		if err := insertOutbox(ctx, tx, event); err != nil {
			return ports.CommitReceipt{}, err
		}
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO experiment_idempotency_receipts(experiment_id, idempotency_key, command_digest, version)
VALUES ($1,$2,$3,$4)`, changes.Experiment.ID, idempotencyKey, commandDigest, changes.Experiment.Version); err != nil {
		return ports.CommitReceipt{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CommitReceipt{}, err
	}
	return ports.CommitReceipt{ExperimentID: changes.Experiment.ID, Version: changes.Experiment.Version}, nil
}

func (s *PostgresStore) Append(
	ctx context.Context,
	fact model.AssignmentFact,
) (model.AssignmentFact, bool, error) {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return model.AssignmentFact{}, false, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	assignedAt, err := parseOptionalTime(fact.AssignedAt)
	if err != nil || assignedAt == nil {
		return model.AssignmentFact{}, false, errors.New("assignment assignedAt is required RFC3339")
	}
	var canonical model.AssignmentFact
	var canonicalAt time.Time
	err = tx.QueryRow(ctx, `
INSERT INTO experiment_assignment_facts(
  id, experiment_id, subject_key, variant, experiment_revision, assigned_at
) VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (experiment_id, experiment_revision, subject_key) DO NOTHING
RETURNING id, experiment_id, subject_key, variant, experiment_revision, assigned_at`,
		fact.ID, fact.ExperimentID, fact.SubjectKey, fact.Variant, fact.ExperimentRevision, assignedAt,
	).Scan(&canonical.ID, &canonical.ExperimentID, &canonical.SubjectKey, &canonical.Variant, &canonical.ExperimentRevision, &canonicalAt)
	inserted := true
	if errors.Is(err, pgx.ErrNoRows) {
		inserted = false
		err = tx.QueryRow(ctx, `
SELECT id, experiment_id, subject_key, variant, experiment_revision, assigned_at
FROM experiment_assignment_facts
WHERE experiment_id=$1 AND experiment_revision=$2 AND subject_key=$3`,
			fact.ExperimentID, fact.ExperimentRevision, fact.SubjectKey,
		).Scan(&canonical.ID, &canonical.ExperimentID, &canonical.SubjectKey, &canonical.Variant, &canonical.ExperimentRevision, &canonicalAt)
	}
	if err != nil {
		return model.AssignmentFact{}, false, err
	}
	canonical.AssignedAt = canonicalAt.UTC().Format(time.RFC3339)
	if err := tx.Commit(ctx); err != nil {
		return model.AssignmentFact{}, false, err
	}
	return canonical, inserted, nil
}

func (s *PostgresStore) Get(
	ctx context.Context,
	experimentID string,
	experimentRevision int64,
	subjectKey string,
) (model.AssignmentFact, error) {
	var out model.AssignmentFact
	var assignedAt time.Time
	err := s.pool.QueryRow(ctx, `
SELECT id, experiment_id, subject_key, variant, experiment_revision, assigned_at
FROM experiment_assignment_facts
WHERE experiment_id=$1 AND experiment_revision=$2 AND subject_key=$3`,
		experimentID, experimentRevision, subjectKey,
	).Scan(&out.ID, &out.ExperimentID, &out.SubjectKey, &out.Variant, &out.ExperimentRevision, &assignedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.AssignmentFact{}, model.ErrAssignmentNotFound
	}
	if err != nil {
		return model.AssignmentFact{}, err
	}
	out.AssignedAt = assignedAt.UTC().Format(time.RFC3339)
	return out, nil
}

func (s *PostgresStore) Stats(ctx context.Context, experimentID string, experimentRevision int64) (ports.AssignmentStats, error) {
	rows, err := s.pool.Query(ctx, `
SELECT variant, COUNT(*) FROM experiment_assignment_facts
WHERE experiment_id=$1 AND experiment_revision=$2 GROUP BY variant ORDER BY variant`, experimentID, experimentRevision)
	if err != nil {
		return ports.AssignmentStats{}, err
	}
	defer rows.Close()
	out := ports.AssignmentStats{VariantCounts: map[string]int{}}
	for rows.Next() {
		var variant string
		var count int
		if err := rows.Scan(&variant, &count); err != nil {
			return ports.AssignmentStats{}, err
		}
		out.VariantCounts[variant] = count
		out.AssignedSubjects += count
	}
	return out, rows.Err()
}

const experimentSelect = `SELECT
  id, key, version, status, variants, audience_rule,
  starts_at, ends_at, created_at, updated_at
FROM experiments`

type rowScanner interface {
	Scan(...any) error
}

func scanExperiment(row rowScanner) (model.Experiment, error) {
	var out model.Experiment
	var variants, audience []byte
	var startsAt, endsAt *time.Time
	var createdAt, updatedAt time.Time
	err := row.Scan(
		&out.ID, &out.Key, &out.Version, &out.Status, &variants, &audience,
		&startsAt, &endsAt, &createdAt, &updatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.Experiment{}, model.ErrNotFound
	}
	if err != nil {
		return model.Experiment{}, err
	}
	if err := json.Unmarshal(variants, &out.Variants); err != nil {
		return model.Experiment{}, err
	}
	if err := json.Unmarshal(audience, &out.AudienceRule); err != nil {
		return model.Experiment{}, err
	}
	out.StartsAt = formatOptionalTime(startsAt)
	out.EndsAt = formatOptionalTime(endsAt)
	out.CreatedAt = createdAt.UTC().Format(time.RFC3339)
	out.UpdatedAt = updatedAt.UTC().Format(time.RFC3339)
	return out, nil
}

func experimentColumns(experiment model.Experiment) ([]byte, []byte, *time.Time, *time.Time, time.Time, time.Time, error) {
	variants, err := json.Marshal(experiment.Variants)
	if err != nil {
		return nil, nil, nil, nil, time.Time{}, time.Time{}, err
	}
	audience, err := json.Marshal(experiment.AudienceRule)
	if err != nil {
		return nil, nil, nil, nil, time.Time{}, time.Time{}, err
	}
	startsAt, err := parseOptionalTime(experiment.StartsAt)
	if err != nil {
		return nil, nil, nil, nil, time.Time{}, time.Time{}, err
	}
	endsAt, err := parseOptionalTime(experiment.EndsAt)
	if err != nil {
		return nil, nil, nil, nil, time.Time{}, time.Time{}, err
	}
	createdAt, err := time.Parse(time.RFC3339, experiment.CreatedAt)
	if err != nil {
		return nil, nil, nil, nil, time.Time{}, time.Time{}, fmt.Errorf("experiment createdAt: %w", err)
	}
	updatedAt, err := time.Parse(time.RFC3339, experiment.UpdatedAt)
	if err != nil {
		return nil, nil, nil, nil, time.Time{}, time.Time{}, fmt.Errorf("experiment updatedAt: %w", err)
	}
	return variants, audience, startsAt, endsAt, createdAt, updatedAt, nil
}

func insertOutbox(ctx context.Context, tx pgx.Tx, event model.Event) error {
	if strings.TrimSpace(event.ID) == "" || strings.TrimSpace(event.Type) == "" {
		return errors.New("outbox event id and type are required")
	}
	_, err := tx.Exec(ctx, `
INSERT INTO product_ops_outbox(
  event_id, event_type, aggregate_type, aggregate_id, payload, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)`,
		event.ID, event.Type, event.AggregateType, event.AggregateID, event.Payload, event.OccurredAt)
	return err
}

func parseOptionalTime(raw string) (*time.Time, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	parsed, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}

func formatOptionalTime(value *time.Time) string {
	if value == nil {
		return ""
	}
	return value.UTC().Format(time.RFC3339)
}

var (
	_ ports.AggregateStore   = (*PostgresStore)(nil)
	_ ports.CatalogReader    = (*PostgresStore)(nil)
	_ ports.AssignmentSink   = (*PostgresStore)(nil)
	_ ports.AssignmentReader = (*PostgresStore)(nil)
)
