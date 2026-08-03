// Package persistence 提供 SkillConsent 对象专属 PostgreSQL Store。
// 授权事实、命令回执与审计事件始终在同一事务内提交。
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

	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
)

type PgStore struct {
	pool *pgxpool.Pool
}

var _ ports.Store = (*PgStore)(nil)

func NewPgStore(pool *pgxpool.Pool) *PgStore {
	return &PgStore{pool: pool}
}

// EnsureSchema 只声明现行单轨 schema。若数据库仍是非 canonical 形态，
// 建索引或查询会失败关闭，不在运行时识别或迁移旧列。
func (store *PgStore) EnsureSchema(ctx context.Context) error {
	if store == nil || store.pool == nil {
		return model.ErrStorageUnavailable
	}
	_, err := store.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS skill_consents (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  granted_scopes JSONB NOT NULL,
  granted_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_consents_account_skill_active
  ON skill_consents(account_id, skill_id)
  WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_skill_consents_account_active
  ON skill_consents(account_id, granted_at DESC)
  WHERE revoked_at IS NULL;
CREATE TABLE IF NOT EXISTS skill_consent_command_receipts (
  receipt_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  operation TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  response_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE(account_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS skill_consent_events (
  event_id TEXT PRIMARY KEY,
  event_name TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_consent_events_aggregate
  ON skill_consent_events(aggregate_id, occurred_at);
`)
	if err != nil {
		return fmt.Errorf("%w: ensure canonical skill consent schema: %v", model.ErrStorageUnavailable, err)
	}
	return nil
}

func (store *PgStore) ListActiveConsents(
	ctx context.Context,
	accountID string,
) ([]model.Consent, error) {
	if store == nil || store.pool == nil {
		return nil, model.ErrStorageUnavailable
	}
	rows, err := store.pool.Query(ctx, `
SELECT id, account_id, skill_id, granted_scopes, granted_at, revoked_at
FROM skill_consents
WHERE account_id = $1 AND revoked_at IS NULL
ORDER BY granted_at DESC`, strings.TrimSpace(accountID))
	if err != nil {
		return nil, fmt.Errorf("%w: list active consents: %v", model.ErrStorageUnavailable, err)
	}
	defer rows.Close()
	items := make([]model.Consent, 0)
	for rows.Next() {
		item, scanErr := scanConsent(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("%w: iterate active consents: %v", model.ErrStorageUnavailable, err)
	}
	return items, nil
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

	if err := lockCommand(ctx, tx, command.AccountID, command.IdempotencyKey); err != nil {
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
	if err := lockAggregate(ctx, tx, command.AccountID, command.SkillID); err != nil {
		return model.MutationResult{}, err
	}

	current, found, err := lockActiveConsent(
		ctx, tx, command.AccountID, command.SkillID,
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	result := model.MutationResult{}
	switch command.Operation {
	case model.CommandGrant:
		if found {
			if !model.EqualScopes(current.GrantedScopes, command.GrantedScopes) {
				return model.MutationResult{}, model.ErrScopeConflict
			}
			result.Consent = &current
			break
		}
		consent := model.Consent{
			ID:            uuid.NewString(),
			AccountID:     command.AccountID,
			SkillID:       command.SkillID,
			GrantedScopes: append([]string(nil), command.GrantedScopes...),
			GrantedAt:     command.OccurredAt,
		}
		grantedScopes, err := json.Marshal(consent.GrantedScopes)
		if err != nil {
			return model.MutationResult{}, unavailable("encode granted scopes", err)
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO skill_consents (
  id, account_id, skill_id, granted_scopes, granted_at, revoked_at
) VALUES ($1, $2, $3, $4, $5, NULL)`,
			consent.ID,
			consent.AccountID,
			consent.SkillID,
			grantedScopes,
			consent.GrantedAt,
		); err != nil {
			return model.MutationResult{}, unavailable("insert consent", err)
		}
		result.Consent = &consent
		result.Changed = true
	case model.CommandRevoke:
		if found {
			revokedAt := command.OccurredAt
			current.RevokedAt = &revokedAt
			tag, err := tx.Exec(ctx, `
UPDATE skill_consents
SET revoked_at = $2
WHERE id = $1 AND revoked_at IS NULL`, current.ID, revokedAt)
			if err != nil {
				return model.MutationResult{}, unavailable("revoke consent", err)
			}
			if tag.RowsAffected() != 1 {
				return model.MutationResult{}, unavailable(
					"revoke consent", errors.New("active consent changed before commit"),
				)
			}
			result.Consent = &current
			result.Changed = true
		}
	default:
		return model.MutationResult{}, model.ErrInvalidArgument
	}

	if result.Changed {
		if err := appendEvent(ctx, tx, command, *result.Consent); err != nil {
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

func lockCommand(
	ctx context.Context,
	tx pgx.Tx,
	accountID, idempotencyKey string,
) error {
	digest := sha256.Sum256([]byte(accountID + "\x1f" + idempotencyKey))
	key := hex.EncodeToString(digest[:])
	if _, err := tx.Exec(
		ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, key,
	); err != nil {
		return unavailable("lock command", err)
	}
	return nil
}

func lockAggregate(
	ctx context.Context,
	tx pgx.Tx,
	accountID, skillID string,
) error {
	digest := sha256.Sum256([]byte(accountID + "\x1f" + skillID))
	key := hex.EncodeToString(digest[:])
	if _, err := tx.Exec(
		ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, key,
	); err != nil {
		return unavailable("lock aggregate", err)
	}
	return nil
}

func loadReceipt(
	ctx context.Context,
	tx pgx.Tx,
	command model.Command,
) (model.MutationResult, bool, error) {
	var operation, requestDigest string
	var payload []byte
	err := tx.QueryRow(ctx, `
SELECT operation, request_digest, response_json
FROM skill_consent_command_receipts
WHERE account_id = $1 AND idempotency_key = $2`,
		command.AccountID, command.IdempotencyKey,
	).Scan(&operation, &requestDigest, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.MutationResult{}, false, nil
	}
	if err != nil {
		return model.MutationResult{}, false, unavailable("load command receipt", err)
	}
	if operation != command.Operation || requestDigest != command.RequestDigest {
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
INSERT INTO skill_consent_command_receipts (
  receipt_id, account_id, idempotency_key, operation,
  request_digest, response_json, created_at
) VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		uuid.NewString(),
		command.AccountID,
		command.IdempotencyKey,
		command.Operation,
		command.RequestDigest,
		payload,
		command.OccurredAt,
	); err != nil {
		return unavailable("save command receipt", err)
	}
	return nil
}

func lockActiveConsent(
	ctx context.Context,
	tx pgx.Tx,
	accountID, skillID string,
) (model.Consent, bool, error) {
	consent, err := scanConsent(tx.QueryRow(ctx, `
SELECT id, account_id, skill_id, granted_scopes, granted_at, revoked_at
FROM skill_consents
WHERE account_id = $1 AND skill_id = $2 AND revoked_at IS NULL
FOR UPDATE`, accountID, skillID))
	if errors.Is(err, pgx.ErrNoRows) {
		return model.Consent{}, false, nil
	}
	if err != nil {
		return model.Consent{}, false, unavailable("lock active consent", err)
	}
	return consent, true, nil
}

func appendEvent(
	ctx context.Context,
	tx pgx.Tx,
	command model.Command,
	consent model.Consent,
) error {
	eventName := model.EventGranted
	if command.Operation == model.CommandRevoke {
		eventName = model.EventRevoked
	}
	event := model.Event{
		EventID:       uuid.NewString(),
		EventName:     eventName,
		AggregateID:   consent.ID,
		AccountID:     consent.AccountID,
		SkillID:       consent.SkillID,
		GrantedScopes: append([]string(nil), consent.GrantedScopes...),
		OccurredAt:    command.OccurredAt,
	}
	payload, err := json.Marshal(event)
	if err != nil {
		return unavailable("encode consent event", err)
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO skill_consent_events (
  event_id, event_name, aggregate_id, account_id,
  skill_id, payload_json, occurred_at
) VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		event.EventID,
		event.EventName,
		event.AggregateID,
		event.AccountID,
		event.SkillID,
		payload,
		event.OccurredAt,
	); err != nil {
		return unavailable("append consent event", err)
	}
	return nil
}

func unavailable(stage string, err error) error {
	return fmt.Errorf("%w: %s: %v", model.ErrStorageUnavailable, stage, err)
}

type rowScanner interface {
	Scan(...any) error
}

func scanConsent(row rowScanner) (model.Consent, error) {
	var consent model.Consent
	var grantedScopes []byte
	if err := row.Scan(
		&consent.ID,
		&consent.AccountID,
		&consent.SkillID,
		&grantedScopes,
		&consent.GrantedAt,
		&consent.RevokedAt,
	); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return model.Consent{}, pgx.ErrNoRows
		}
		return model.Consent{}, unavailable("scan active consent", err)
	}
	if err := json.Unmarshal(grantedScopes, &consent.GrantedScopes); err != nil ||
		len(consent.GrantedScopes) == 0 {
		if err == nil {
			err = errors.New("granted scopes are empty")
		}
		return model.Consent{}, unavailable("decode granted scopes", err)
	}
	return consent, nil
}
