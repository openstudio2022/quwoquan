// Package persistence 提供 SkillSurfacePlacement 的唯一 PostgreSQL Store。
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

	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/ports"
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
CREATE TABLE IF NOT EXISTS skill_surface_placements (
  id TEXT PRIMARY KEY,
  surface_kind TEXT NOT NULL,
  surface_id TEXT NOT NULL,
  policy TEXT NOT NULL,
  disabled_skill_ids JSONB NOT NULL,
  status TEXT NOT NULL,
  revision BIGINT NOT NULL,
  created_by_account_id TEXT NOT NULL,
  updated_by_account_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(surface_kind, surface_id)
);
CREATE INDEX IF NOT EXISTS idx_skill_surface_placements_status_updated
  ON skill_surface_placements(status, updated_at DESC);
CREATE TABLE IF NOT EXISTS skill_surface_placement_command_receipts (
  receipt_id TEXT PRIMARY KEY,
  surface_kind TEXT NOT NULL,
  surface_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  operation TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  response_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE(surface_kind, surface_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS skill_surface_placement_outbox (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  aggregate_revision BIGINT NOT NULL,
  payload_json JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  dispatched_at TIMESTAMPTZ NULL,
  UNIQUE(aggregate_id, aggregate_revision, event_type)
);
CREATE INDEX IF NOT EXISTS idx_skill_surface_placement_outbox_pending
  ON skill_surface_placement_outbox(dispatched_at, occurred_at);
`)
	if err != nil {
		return unavailable("ensure canonical schema", err)
	}
	return nil
}

func (store *PgStore) Get(
	ctx context.Context,
	surfaceKind string,
	surfaceID string,
) (model.Placement, error) {
	if store == nil || store.pool == nil {
		return model.Placement{}, model.ErrStorageUnavailable
	}
	return scanPlacement(store.pool.QueryRow(ctx, `
SELECT id, surface_kind, surface_id, policy, disabled_skill_ids, status,
       revision, created_by_account_id, updated_by_account_id, created_at, updated_at
FROM skill_surface_placements
WHERE surface_kind=$1 AND surface_id=$2`,
		strings.TrimSpace(surfaceKind),
		strings.TrimSpace(surfaceID),
	))
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
	if err := advisoryLock(
		ctx,
		tx,
		command.SurfaceKind+"\x1f"+command.SurfaceID,
		command.IdempotencyKey,
	); err != nil {
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
	if err := advisoryLock(ctx, tx, command.SurfaceKind, command.SurfaceID); err != nil {
		return model.MutationResult{}, err
	}
	current, found, err := lockPlacement(ctx, tx, command.SurfaceKind, command.SurfaceID)
	if err != nil {
		return model.MutationResult{}, err
	}
	if (!found && command.ExpectedRevision != 0) ||
		(found && current.Revision != command.ExpectedRevision) {
		return model.MutationResult{}, model.ErrRevisionConflict
	}
	result := model.MutationResult{}
	if !found {
		result.Placement = model.Placement{
			ID:                 uuid.NewString(),
			SurfaceKind:        command.SurfaceKind,
			SurfaceID:          command.SurfaceID,
			Policy:             command.Policy,
			DisabledSkillIDs:   append([]string(nil), command.DisabledSkillIDs...),
			Status:             command.Status,
			Revision:           1,
			CreatedByAccountID: command.ActorAccountID,
			UpdatedByAccountID: command.ActorAccountID,
			CreatedAt:          command.OccurredAt,
			UpdatedAt:          command.OccurredAt,
		}
		disabled, _ := json.Marshal(result.Placement.DisabledSkillIDs)
		if _, err := tx.Exec(ctx, `
INSERT INTO skill_surface_placements (
  id, surface_kind, surface_id, policy, disabled_skill_ids, status,
  revision, created_by_account_id, updated_by_account_id, created_at, updated_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
			result.Placement.ID,
			result.Placement.SurfaceKind,
			result.Placement.SurfaceID,
			result.Placement.Policy,
			disabled,
			result.Placement.Status,
			result.Placement.Revision,
			result.Placement.CreatedByAccountID,
			result.Placement.UpdatedByAccountID,
			result.Placement.CreatedAt,
			result.Placement.UpdatedAt,
		); err != nil {
			return model.MutationResult{}, unavailable("insert placement", err)
		}
		result.Changed = true
	} else if current.Equivalent(command) {
		result.Placement = current
	} else {
		current.Policy = command.Policy
		current.DisabledSkillIDs = append([]string(nil), command.DisabledSkillIDs...)
		current.Status = command.Status
		current.Revision++
		current.UpdatedByAccountID = command.ActorAccountID
		current.UpdatedAt = command.OccurredAt
		disabled, _ := json.Marshal(current.DisabledSkillIDs)
		tag, err := tx.Exec(ctx, `
UPDATE skill_surface_placements
SET policy=$1, disabled_skill_ids=$2, status=$3, revision=$4,
    updated_by_account_id=$5, updated_at=$6
WHERE id=$7 AND revision=$8`,
			current.Policy,
			disabled,
			current.Status,
			current.Revision,
			current.UpdatedByAccountID,
			current.UpdatedAt,
			current.ID,
			command.ExpectedRevision,
		)
		if err != nil {
			return model.MutationResult{}, unavailable("update placement", err)
		}
		if tag.RowsAffected() != 1 {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		result.Placement = current
		result.Changed = true
	}
	if result.Changed {
		if err := appendOutbox(ctx, tx, result.Placement); err != nil {
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

func scanPlacement(row rowScanner) (model.Placement, error) {
	var placement model.Placement
	var disabled []byte
	err := row.Scan(
		&placement.ID,
		&placement.SurfaceKind,
		&placement.SurfaceID,
		&placement.Policy,
		&disabled,
		&placement.Status,
		&placement.Revision,
		&placement.CreatedByAccountID,
		&placement.UpdatedByAccountID,
		&placement.CreatedAt,
		&placement.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.Placement{}, model.ErrNotFound
	}
	if err != nil {
		return model.Placement{}, unavailable("scan placement", err)
	}
	if err := json.Unmarshal(disabled, &placement.DisabledSkillIDs); err != nil {
		return model.Placement{}, unavailable("decode disabled Skill IDs", err)
	}
	return placement, nil
}

func lockPlacement(
	ctx context.Context,
	tx pgx.Tx,
	surfaceKind string,
	surfaceID string,
) (model.Placement, bool, error) {
	placement, err := scanPlacement(tx.QueryRow(ctx, `
SELECT id, surface_kind, surface_id, policy, disabled_skill_ids, status,
       revision, created_by_account_id, updated_by_account_id, created_at, updated_at
FROM skill_surface_placements
WHERE surface_kind=$1 AND surface_id=$2
FOR UPDATE`, surfaceKind, surfaceID))
	if errors.Is(err, model.ErrNotFound) {
		return model.Placement{}, false, nil
	}
	if err != nil {
		return model.Placement{}, false, err
	}
	return placement, true, nil
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
FROM skill_surface_placement_command_receipts
WHERE surface_kind=$1 AND surface_id=$2 AND idempotency_key=$3`,
		command.SurfaceKind,
		command.SurfaceID,
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
INSERT INTO skill_surface_placement_command_receipts (
  receipt_id, surface_kind, surface_id, idempotency_key,
  operation, request_digest, response_json, created_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		uuid.NewString(),
		command.SurfaceKind,
		command.SurfaceID,
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

func appendOutbox(ctx context.Context, tx pgx.Tx, placement model.Placement) error {
	payload, err := json.Marshal(map[string]any{
		"id":               placement.ID,
		"surfaceKind":      placement.SurfaceKind,
		"surfaceId":        placement.SurfaceID,
		"policy":           placement.Policy,
		"disabledSkillIds": placement.DisabledSkillIDs,
		"status":           placement.Status,
		"revision":         placement.Revision,
		"updatedAt":        placement.UpdatedAt,
	})
	if err != nil {
		return unavailable("encode outbox event", err)
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO skill_surface_placement_outbox (
  event_id, event_type, aggregate_id, aggregate_revision,
  payload_json, occurred_at, dispatched_at
) VALUES ($1,$2,$3,$4,$5,$6,NULL)`,
		uuid.NewString(),
		model.EventChanged,
		placement.ID,
		placement.Revision,
		payload,
		placement.UpdatedAt,
	); err != nil {
		return unavailable("append outbox event", err)
	}
	return nil
}

func unavailable(action string, err error) error {
	return fmt.Errorf("%w: %s: %v", model.ErrStorageUnavailable, action, err)
}
