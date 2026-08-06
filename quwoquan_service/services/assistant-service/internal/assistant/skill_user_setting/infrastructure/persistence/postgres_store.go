// Package persistence 提供 SkillUserSetting 的唯一 PostgreSQL Store。
// 聚合、CAS、幂等回执和 outbox 始终在同一事务提交。
package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/ports"
)

type PgStore struct {
	pool *pgxpool.Pool
}

var _ ports.Store = (*PgStore)(nil)

func NewPgStore(pool *pgxpool.Pool) *PgStore { return &PgStore{pool: pool} }

func (store *PgStore) EnsureSchema(ctx context.Context) error {
	if store == nil || store.pool == nil {
		return model.ErrStorageUnavailable
	}
	_, err := store.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS skill_user_settings (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  status TEXT NOT NULL,
  configuration_data JSONB NOT NULL,
  configuration_schema_digest TEXT NOT NULL,
  memory_policy TEXT NOT NULL,
  connector_connection_refs JSONB NOT NULL,
  revision BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(account_id, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_skill_user_settings_account_status
  ON skill_user_settings(account_id, status, updated_at DESC);
CREATE TABLE IF NOT EXISTS skill_user_setting_command_receipts (
  receipt_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  operation TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  response_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE(account_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS skill_user_setting_outbox (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  aggregate_revision BIGINT NOT NULL,
  payload_json JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  dispatched_at TIMESTAMPTZ NULL,
	claim_owner TEXT NULL,
	claimed_at TIMESTAMPTZ NULL,
	next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	attempt_count INTEGER NOT NULL DEFAULT 0,
	last_error_code TEXT NULL,
  UNIQUE(aggregate_id, aggregate_revision, event_type)
);
ALTER TABLE skill_user_setting_outbox
  ADD COLUMN IF NOT EXISTS claim_owner TEXT NULL,
  ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_error_code TEXT NULL;
CREATE INDEX IF NOT EXISTS idx_skill_user_setting_outbox_pending
  ON skill_user_setting_outbox(dispatched_at, occurred_at);
CREATE INDEX IF NOT EXISTS idx_skill_user_setting_outbox_delivery_head
  ON skill_user_setting_outbox(dispatched_at, next_attempt_at, occurred_at, event_id);
`)
	if err != nil {
		return unavailable("ensure canonical schema", err)
	}
	return nil
}

func (store *PgStore) Get(
	ctx context.Context,
	accountID string,
	skillID string,
) (model.Setting, error) {
	if store == nil || store.pool == nil {
		return model.Setting{}, model.ErrStorageUnavailable
	}
	return scanSetting(store.pool.QueryRow(ctx, `
SELECT id, account_id, skill_id, status, configuration_data,
       configuration_schema_digest, memory_policy, connector_connection_refs,
       revision, created_at, updated_at
FROM skill_user_settings
WHERE account_id = $1 AND skill_id = $2`,
		strings.TrimSpace(accountID),
		strings.TrimSpace(skillID),
	))
}

func (store *PgStore) List(
	ctx context.Context,
	accountID string,
	limit int,
) ([]model.Setting, error) {
	if store == nil || store.pool == nil {
		return nil, model.ErrStorageUnavailable
	}
	rows, err := store.pool.Query(ctx, `
SELECT id, account_id, skill_id, status, configuration_data,
       configuration_schema_digest, memory_policy, connector_connection_refs,
       revision, created_at, updated_at
FROM skill_user_settings
WHERE account_id = $1
ORDER BY skill_id ASC
LIMIT $2`, strings.TrimSpace(accountID), limit)
	if err != nil {
		return nil, unavailable("list settings", err)
	}
	defer rows.Close()
	settings := make([]model.Setting, 0)
	for rows.Next() {
		setting, scanErr := scanSetting(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		settings = append(settings, setting)
	}
	if err := rows.Err(); err != nil {
		return nil, unavailable("iterate settings", err)
	}
	return settings, nil
}

func (store *PgStore) Apply(
	ctx context.Context,
	command model.Command,
) (model.MutationResult, error) {
	if store == nil || store.pool == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return model.MutationResult{}, unavailable("begin transaction", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()
	if err := advisoryLock(ctx, tx, command.AccountID, command.IdempotencyKey); err != nil {
		return model.MutationResult{}, err
	}
	if replay, found, err := loadReceipt(ctx, tx, command); err != nil {
		return model.MutationResult{}, err
	} else if found {
		if err := tx.Commit(ctx); err != nil {
			return model.MutationResult{}, unavailable("commit replay", err)
		}
		committed = true
		replay.Replayed = true
		return replay, nil
	}
	if err := advisoryLock(ctx, tx, command.AccountID, command.SkillID); err != nil {
		return model.MutationResult{}, err
	}
	current, found, err := lockSetting(ctx, tx, command.AccountID, command.SkillID)
	if err != nil {
		return model.MutationResult{}, err
	}
	if (!found && command.ExpectedRevision != 0) ||
		(found && current.Revision != command.ExpectedRevision) {
		return model.MutationResult{}, model.ErrRevisionConflict
	}
	result := model.MutationResult{}
	if !found {
		result.Setting = model.Setting{
			ID:                        uuid.NewString(),
			AccountID:                 command.AccountID,
			SkillID:                   command.SkillID,
			Status:                    command.Status,
			ConfigurationData:         append(json.RawMessage(nil), command.ConfigurationData...),
			ConfigurationSchemaDigest: command.ConfigurationSchemaDigest,
			MemoryPolicy:              command.MemoryPolicy,
			ConnectorConnectionRefs:   append([]string(nil), command.ConnectorConnectionRefs...),
			Revision:                  1,
			CreatedAt:                 command.OccurredAt,
			UpdatedAt:                 command.OccurredAt,
		}
		connectors, _ := json.Marshal(result.Setting.ConnectorConnectionRefs)
		if _, err := tx.Exec(ctx, `
INSERT INTO skill_user_settings (
  id, account_id, skill_id, status, configuration_data,
  configuration_schema_digest, memory_policy, connector_connection_refs,
  revision, created_at, updated_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
			result.Setting.ID,
			result.Setting.AccountID,
			result.Setting.SkillID,
			result.Setting.Status,
			[]byte(result.Setting.ConfigurationData),
			result.Setting.ConfigurationSchemaDigest,
			result.Setting.MemoryPolicy,
			connectors,
			result.Setting.Revision,
			result.Setting.CreatedAt,
			result.Setting.UpdatedAt,
		); err != nil {
			return model.MutationResult{}, unavailable("insert setting", err)
		}
		result.Changed = true
	} else if current.Equivalent(command) {
		result.Setting = current
	} else {
		current.Status = command.Status
		current.ConfigurationData = append(json.RawMessage(nil), command.ConfigurationData...)
		current.ConfigurationSchemaDigest = command.ConfigurationSchemaDigest
		current.MemoryPolicy = command.MemoryPolicy
		current.ConnectorConnectionRefs = append([]string(nil), command.ConnectorConnectionRefs...)
		current.Revision++
		current.UpdatedAt = command.OccurredAt
		connectors, _ := json.Marshal(current.ConnectorConnectionRefs)
		tag, err := tx.Exec(ctx, `
UPDATE skill_user_settings
SET status=$1, configuration_data=$2, configuration_schema_digest=$3,
    memory_policy=$4, connector_connection_refs=$5, revision=$6, updated_at=$7
WHERE id=$8 AND revision=$9`,
			current.Status,
			[]byte(current.ConfigurationData),
			current.ConfigurationSchemaDigest,
			current.MemoryPolicy,
			connectors,
			current.Revision,
			current.UpdatedAt,
			current.ID,
			command.ExpectedRevision,
		)
		if err != nil {
			return model.MutationResult{}, unavailable("update setting", err)
		}
		if tag.RowsAffected() != 1 {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		result.Setting = current
		result.Changed = true
	}
	if result.Changed {
		if err := appendOutbox(ctx, tx, result.Setting); err != nil {
			return model.MutationResult{}, err
		}
	}
	if err := saveReceipt(ctx, tx, command, result); err != nil {
		return model.MutationResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return model.MutationResult{}, unavailable("commit command", err)
	}
	committed = true
	return result, nil
}

type rowScanner interface {
	Scan(...any) error
}

func scanSetting(row rowScanner) (model.Setting, error) {
	var setting model.Setting
	var configuration []byte
	var connectors []byte
	err := row.Scan(
		&setting.ID,
		&setting.AccountID,
		&setting.SkillID,
		&setting.Status,
		&configuration,
		&setting.ConfigurationSchemaDigest,
		&setting.MemoryPolicy,
		&connectors,
		&setting.Revision,
		&setting.CreatedAt,
		&setting.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.Setting{}, model.ErrNotFound
	}
	if err != nil {
		return model.Setting{}, unavailable("scan setting", err)
	}
	if err := json.Unmarshal(connectors, &setting.ConnectorConnectionRefs); err != nil {
		return model.Setting{}, unavailable("decode connector refs", err)
	}
	setting.ConfigurationData = append(json.RawMessage(nil), configuration...)
	return setting, nil
}

func lockSetting(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	skillID string,
) (model.Setting, bool, error) {
	setting, err := scanSetting(tx.QueryRow(ctx, `
SELECT id, account_id, skill_id, status, configuration_data,
       configuration_schema_digest, memory_policy, connector_connection_refs,
       revision, created_at, updated_at
FROM skill_user_settings
WHERE account_id=$1 AND skill_id=$2
FOR UPDATE`, accountID, skillID))
	if errors.Is(err, model.ErrNotFound) {
		return model.Setting{}, false, nil
	}
	if err != nil {
		return model.Setting{}, false, err
	}
	return setting, true, nil
}

func advisoryLock(ctx context.Context, tx pgx.Tx, left string, right string) error {
	sum := sha256.Sum256([]byte(left + "\x1f" + right))
	key := hex.EncodeToString(sum[:])
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, key); err != nil {
		return unavailable("acquire advisory lock", err)
	}
	return nil
}

func loadReceipt(
	ctx context.Context,
	tx pgx.Tx,
	command model.Command,
) (model.MutationResult, bool, error) {
	var operation string
	var requestDigest string
	var payload []byte
	err := tx.QueryRow(ctx, `
SELECT operation, request_digest, response_json
FROM skill_user_setting_command_receipts
WHERE account_id=$1 AND idempotency_key=$2`,
		command.AccountID,
		command.IdempotencyKey,
	).Scan(&operation, &requestDigest, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.MutationResult{}, false, nil
	}
	if err != nil {
		return model.MutationResult{}, false, unavailable("load command receipt", err)
	}
	if operation != model.CommandPut || requestDigest != command.RequestDigest {
		return model.MutationResult{}, false, model.ErrIdempotencyConflict
	}
	var result model.MutationResult
	if err := json.Unmarshal(payload, &result); err != nil {
		return model.MutationResult{}, false, unavailable("decode command receipt", err)
	}
	return result, true, nil
}

func saveReceipt(
	ctx context.Context,
	tx pgx.Tx,
	command model.Command,
	result model.MutationResult,
) error {
	payload, err := json.Marshal(result)
	if err != nil {
		return unavailable("encode command receipt", err)
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO skill_user_setting_command_receipts (
  receipt_id, account_id, idempotency_key, operation,
  request_digest, response_json, created_at
) VALUES ($1,$2,$3,$4,$5,$6,$7)`,
		uuid.NewString(),
		command.AccountID,
		command.IdempotencyKey,
		model.CommandPut,
		command.RequestDigest,
		payload,
		command.OccurredAt,
	); err != nil {
		return unavailable("save command receipt", err)
	}
	return nil
}

func appendOutbox(ctx context.Context, tx pgx.Tx, setting model.Setting) error {
	payload, err := json.Marshal(map[string]any{
		"id":                        setting.ID,
		"accountId":                 setting.AccountID,
		"skillId":                   setting.SkillID,
		"status":                    setting.Status,
		"configurationSchemaDigest": setting.ConfigurationSchemaDigest,
		"memoryPolicy":              setting.MemoryPolicy,
		"connectorConnectionRefs":   setting.ConnectorConnectionRefs,
		"revision":                  setting.Revision,
		"updatedAt":                 setting.UpdatedAt,
	})
	if err != nil {
		return unavailable("encode outbox event", err)
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO skill_user_setting_outbox (
  event_id, event_type, aggregate_id, aggregate_revision,
  payload_json, occurred_at, dispatched_at
) VALUES ($1,$2,$3,$4,$5,$6,NULL)`,
		uuid.NewString(),
		model.EventChanged,
		setting.ID,
		setting.Revision,
		payload,
		setting.UpdatedAt,
	); err != nil {
		return unavailable("append outbox event", err)
	}
	return nil
}

func unavailable(action string, err error) error {
	return fmt.Errorf("%w: %s: %v", model.ErrStorageUnavailable, action, err)
}
