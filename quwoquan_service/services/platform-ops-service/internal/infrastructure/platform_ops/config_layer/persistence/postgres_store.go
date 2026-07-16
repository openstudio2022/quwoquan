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

	"quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
	"quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("config layer postgres pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (s *PostgresStore) EnsureSchema(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS platform_config_layers (
  id VARCHAR(160) PRIMARY KEY,
  version BIGINT NOT NULL,
  scope_level VARCHAR(32) NOT NULL,
  scope_id VARCHAR(160) NOT NULL,
  environment VARCHAR(64) NULL,
  cluster VARCHAR(128) NULL,
  service VARCHAR(128) NULL,
  entries JSONB NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE platform_config_layers DROP CONSTRAINT IF EXISTS uq_platform_config_scope;
CREATE UNIQUE INDEX IF NOT EXISTS uq_platform_config_scope
  ON platform_config_layers(
    scope_level,
    COALESCE(environment,''),
    COALESCE(cluster,''),
    COALESCE(service,'')
  );
CREATE INDEX IF NOT EXISTS idx_platform_config_resolution
  ON platform_config_layers(environment, cluster, service);
CREATE TABLE IF NOT EXISTS platform_config_layer_receipts (
  layer_id VARCHAR(160) NOT NULL,
  idempotency_key VARCHAR(160) NOT NULL,
  command_digest VARCHAR(64) NOT NULL,
  version BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(layer_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS platform_ops_outbox (
  event_id VARCHAR(128) PRIMARY KEY,
  event_type VARCHAR(128) NOT NULL,
  aggregate_type VARCHAR(128) NOT NULL,
  aggregate_id VARCHAR(160) NOT NULL,
  payload JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  dispatched_at TIMESTAMPTZ NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_platform_ops_outbox_ready
  ON platform_ops_outbox(dispatched_at, next_attempt_at, occurred_at);
`)
	return err
}

func (s *PostgresStore) Load(ctx context.Context, id string) (model.ConfigLayer, error) {
	row := s.pool.QueryRow(ctx, `
SELECT id, version, scope_level, scope_id,
  COALESCE(environment,''), COALESCE(cluster,''), COALESCE(service,''),
  entries, status, created_at, updated_at
FROM platform_config_layers WHERE id=$1`, strings.TrimSpace(id))
	return scanConfigLayer(row)
}

func (s *PostgresStore) List(ctx context.Context) ([]model.ConfigLayer, error) {
	rows, err := s.pool.Query(ctx, `
SELECT id, version, scope_level, scope_id,
  COALESCE(environment,''), COALESCE(cluster,''), COALESCE(service,''),
  entries, status, created_at, updated_at
FROM platform_config_layers ORDER BY scope_level, scope_id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]model.ConfigLayer, 0)
	for rows.Next() {
		layer, err := scanConfigLayer(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, layer)
	}
	return items, rows.Err()
}

func (s *PostgresStore) Replay(
	ctx context.Context,
	layerID, idempotencyKey, commandDigest string,
) (ports.CommitReceipt, bool, error) {
	if err := validateIdempotency(layerID, idempotencyKey, commandDigest); err != nil {
		return ports.CommitReceipt{}, false, err
	}
	var receipt ports.CommitReceipt
	var storedDigest string
	err := s.pool.QueryRow(ctx, `
SELECT layer_id, version, command_digest
FROM platform_config_layer_receipts
WHERE layer_id=$1 AND idempotency_key=$2`, layerID, idempotencyKey).Scan(
		&receipt.LayerID, &receipt.Version, &storedDigest,
	)
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
	if err := validateIdempotency(changes.Layer.ID, changes.IdempotencyKey, changes.CommandDigest); err != nil {
		return ports.CommitReceipt{}, err
	}
	if err := changes.Layer.Validate(); err != nil {
		return ports.CommitReceipt{}, err
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if receipt, found, err := replayTx(ctx, tx, changes.Layer.ID, changes.IdempotencyKey, changes.CommandDigest); err != nil {
		return ports.CommitReceipt{}, err
	} else if found {
		if err := tx.Commit(ctx); err != nil {
			return ports.CommitReceipt{}, err
		}
		return receipt, nil
	}
	entries, err := json.Marshal(changes.Layer.Entries)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	createdAt, err := time.Parse(time.RFC3339, changes.Layer.CreatedAt)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	updatedAt, err := time.Parse(time.RFC3339, changes.Layer.UpdatedAt)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if expectedVersion == 0 {
		if changes.Layer.Version != 1 {
			return ports.CommitReceipt{}, model.ErrVersionConflict
		}
		command, err := tx.Exec(ctx, `
INSERT INTO platform_config_layers(
  id,version,scope_level,scope_id,environment,cluster,service,entries,status,created_at,updated_at
) VALUES($1,$2,$3,$4,NULLIF($5,''),NULLIF($6,''),NULLIF($7,''),$8,$9,$10,$11)
ON CONFLICT DO NOTHING`,
			changes.Layer.ID, changes.Layer.Version, changes.Layer.Scope.Level, changes.Layer.Scope.ID,
			changes.Layer.Scope.Environment, changes.Layer.Scope.Cluster, changes.Layer.Scope.Service,
			entries, changes.Layer.Status, createdAt, updatedAt,
		)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		if command.RowsAffected() != 1 {
			return ports.CommitReceipt{}, model.ErrVersionConflict
		}
	} else {
		command, err := tx.Exec(ctx, `
UPDATE platform_config_layers SET
  version=$2, entries=$3, status=$4, updated_at=$5
WHERE id=$1 AND version=$6`, changes.Layer.ID, changes.Layer.Version, entries,
			changes.Layer.Status, updatedAt, expectedVersion)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		if command.RowsAffected() != 1 {
			return ports.CommitReceipt{}, model.ErrVersionConflict
		}
	}
	for _, event := range changes.Events {
		if _, err := tx.Exec(ctx, `
INSERT INTO platform_ops_outbox(
  event_id,event_type,aggregate_type,aggregate_id,payload,occurred_at
) VALUES($1,$2,$3,$4,$5,$6)`, event.ID, event.Type, event.AggregateType,
			event.AggregateID, event.Payload, event.OccurredAt); err != nil {
			return ports.CommitReceipt{}, err
		}
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO platform_config_layer_receipts(
  layer_id,idempotency_key,command_digest,version
) VALUES($1,$2,$3,$4)`, changes.Layer.ID, changes.IdempotencyKey,
		changes.CommandDigest, changes.Layer.Version); err != nil {
		return ports.CommitReceipt{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CommitReceipt{}, err
	}
	return ports.CommitReceipt{LayerID: changes.Layer.ID, Version: changes.Layer.Version}, nil
}

type rowScanner interface {
	Scan(...any) error
}

func scanConfigLayer(row rowScanner) (model.ConfigLayer, error) {
	var layer model.ConfigLayer
	var entries []byte
	var createdAt, updatedAt time.Time
	err := row.Scan(
		&layer.ID, &layer.Version, &layer.Scope.Level, &layer.Scope.ID,
		&layer.Scope.Environment, &layer.Scope.Cluster, &layer.Scope.Service,
		&entries, &layer.Status, &createdAt, &updatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.ConfigLayer{}, model.ErrNotFound
	}
	if err != nil {
		return model.ConfigLayer{}, err
	}
	if err := json.Unmarshal(entries, &layer.Entries); err != nil {
		return model.ConfigLayer{}, err
	}
	layer.CreatedAt = createdAt.UTC().Format(time.RFC3339)
	layer.UpdatedAt = updatedAt.UTC().Format(time.RFC3339)
	return layer, layer.Validate()
}

func replayTx(
	ctx context.Context,
	tx pgx.Tx,
	layerID, idempotencyKey, commandDigest string,
) (ports.CommitReceipt, bool, error) {
	var receipt ports.CommitReceipt
	var storedDigest string
	err := tx.QueryRow(ctx, `
SELECT layer_id, version, command_digest
FROM platform_config_layer_receipts
WHERE layer_id=$1 AND idempotency_key=$2 FOR UPDATE`, layerID, idempotencyKey).Scan(
		&receipt.LayerID, &receipt.Version, &storedDigest,
	)
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

func validateIdempotency(layerID, key, digest string) error {
	if strings.TrimSpace(layerID) == "" || strings.TrimSpace(key) == "" || strings.TrimSpace(digest) == "" {
		return fmt.Errorf("layer id, idempotency key and command digest are required")
	}
	if len(key) > 160 {
		return fmt.Errorf("idempotency key exceeds 160 characters")
	}
	return nil
}

var (
	_ ports.AggregateStore = (*PostgresStore)(nil)
	_ ports.LayerReader    = (*PostgresStore)(nil)
)
