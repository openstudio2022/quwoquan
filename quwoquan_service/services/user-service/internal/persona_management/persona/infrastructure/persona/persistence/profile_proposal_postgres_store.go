package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

type ProfileProposalPostgresStore struct {
	pool *pgxpool.Pool
}

func NewProfileProposalPostgresStore(pool *pgxpool.Pool) (*ProfileProposalPostgresStore, error) {
	if pool == nil {
		return nil, errors.New("Persona PostgreSQL pool is required")
	}
	return &ProfileProposalPostgresStore{pool: pool}, nil
}

func (s *ProfileProposalPostgresStore) CurrentVersion(
	ctx context.Context,
	personaID string,
) (int64, error) {
	var (
		version int64
		status  string
	)
	err := s.pool.QueryRow(ctx, `
SELECT version, status
FROM personas
WHERE persona_id=$1`, strings.TrimSpace(personaID)).Scan(&version, &status)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, personamodel.ErrNotFound
	}
	if err != nil {
		return 0, err
	}
	if status == "retired" {
		return 0, personamodel.ErrRetired
	}
	if version <= 0 {
		return 0, personamodel.ErrInvalidArgument
	}
	return version, nil
}

func (s *ProfileProposalPostgresStore) ApplyProfileProposal(
	ctx context.Context,
	command personaports.ApplyProfileProposalCommand,
	commandDigest string,
) (personaports.ProfileProposalMutationResult, error) {
	commandDigest = strings.TrimSpace(commandDigest)
	if commandDigest == "" {
		return personaports.ProfileProposalMutationResult{},
			errors.New("Persona command digest is required")
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	commandKey := personaProposalCommandKey(command.ProposalID, "apply")
	if replayed, found, err := personaProposalReplay(ctx, tx, commandKey, commandDigest); err != nil || found {
		return finishPersonaReplay(ctx, tx, replayed, found, err)
	}

	var (
		before personamodel.ProfileSnapshot
		status string
	)
	err = tx.QueryRow(ctx, `
SELECT display_name, bio, avatar_media_asset_id, COALESCE(avatar_url,''),
       background_media_asset_id, COALESCE(background_url,''),
       is_private, isolation_level, purpose_hint, version, status
FROM personas
WHERE persona_id=$1
FOR UPDATE`, command.PersonaID).Scan(
		&before.DisplayName,
		&before.Bio,
		&before.AvatarMediaAssetID,
		&before.AvatarURL,
		&before.BackgroundMediaAssetID,
		&before.BackgroundURL,
		&before.IsPrivate,
		&before.IsolationLevel,
		&before.PurposeHint,
		&before.Version,
		&status,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrNotFound
	}
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	// The row lock may have waited behind a transaction that committed the same
	// proposal receipt. Re-read after locking before evaluating the version.
	if replayed, found, err := personaProposalReplay(ctx, tx, commandKey, commandDigest); err != nil || found {
		return finishPersonaReplay(ctx, tx, replayed, found, err)
	}
	if status == "retired" {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrRetired
	}
	if before.Version != command.ExpectedPersonaVersion {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrVersionConflict
	}

	changes := command.Changes
	occurredAt := time.Now().UTC()
	after := applyProfileChangeSet(before, changes)
	after.Version = before.Version + 1
	result, err := tx.Exec(ctx, `
UPDATE personas SET
  display_name=CASE WHEN $3 THEN $4 ELSE display_name END,
  bio=CASE WHEN $5 THEN $6 ELSE bio END,
  avatar_media_asset_id=CASE WHEN $7 THEN $8 ELSE avatar_media_asset_id END,
  avatar_url=CASE WHEN $7 THEN '' ELSE avatar_url END,
  background_media_asset_id=CASE WHEN $9 THEN $10 ELSE background_media_asset_id END,
  background_url=CASE WHEN $9 THEN '' ELSE background_url END,
  is_private=CASE WHEN $11 THEN $12 ELSE is_private END,
  isolation_level=CASE WHEN $13 THEN $14 ELSE isolation_level END,
  purpose_hint=CASE WHEN $15 THEN $16 ELSE purpose_hint END,
  version=$2,
  updated_at=$17
WHERE persona_id=$1 AND version=$18`,
		command.PersonaID,
		after.Version,
		changes.DisplayName != nil,
		stringValue(changes.DisplayName),
		changes.Bio != nil,
		stringValue(changes.Bio),
		changes.AvatarMediaAssetID != nil,
		stringValue(changes.AvatarMediaAssetID),
		changes.BackgroundMediaAssetID != nil,
		stringValue(changes.BackgroundMediaAssetID),
		changes.IsPrivate != nil,
		boolValue(changes.IsPrivate),
		changes.IsolationLevel != nil,
		stringValue(changes.IsolationLevel),
		changes.PurposeHint != nil,
		stringValue(changes.PurposeHint),
		occurredAt,
		before.Version,
	)
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	if result.RowsAffected() != 1 {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrVersionConflict
	}

	mutation := personaports.ProfileProposalMutationResult{
		Before: before, After: after, OccurredAt: occurredAt,
	}
	eventPayload, err := json.Marshal(struct {
		ProposalID string `json:"proposalId"`
		PersonaID  string `json:"personaId"`
		Version    int64  `json:"version"`
	}{
		ProposalID: command.ProposalID,
		PersonaID:  command.PersonaID,
		Version:    mutation.After.Version,
	})
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	eventID := stablePersonaPacketID("apply-event", command.ProposalID)
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,'PersonaUpdated',$4,$5)`,
		eventID, command.PersonaID, after.Version, eventPayload, occurredAt,
	); err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	resultJSON, err := json.Marshal(mutation)
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_command_receipts(
  receipt_id, aggregate_id, idempotency_key, command_digest, aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6)`,
		stablePersonaPacketID("apply-receipt", command.ProposalID),
		command.PersonaID,
		commandKey,
		commandDigest,
		after.Version,
		resultJSON,
	); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return personaports.ProfileProposalMutationResult{}, personamodel.ErrIdempotencyConflict
		}
		return personaports.ProfileProposalMutationResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	return mutation, nil
}

func (s *ProfileProposalPostgresStore) RollbackProfileProposal(
	ctx context.Context,
	command personaports.RollbackProfileProposalCommand,
	commandDigest string,
) (personaports.ProfileProposalMutationResult, error) {
	commandDigest = strings.TrimSpace(commandDigest)
	if commandDigest == "" {
		return personaports.ProfileProposalMutationResult{},
			errors.New("Persona command digest is required")
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	commandKey := personaProposalCommandKey(command.ProposalID, "rollback")
	if replayed, found, err := personaProposalReplay(
		ctx,
		tx,
		commandKey,
		commandDigest,
	); err != nil || found {
		return finishPersonaReplay(ctx, tx, replayed, found, err)
	}

	var (
		before personamodel.ProfileSnapshot
		status string
	)
	err = tx.QueryRow(ctx, `
SELECT display_name, bio, avatar_media_asset_id, COALESCE(avatar_url,''),
       background_media_asset_id, COALESCE(background_url,''),
       is_private, isolation_level, purpose_hint, version, status
FROM personas
WHERE persona_id=$1
FOR UPDATE`, command.PersonaID).Scan(
		&before.DisplayName,
		&before.Bio,
		&before.AvatarMediaAssetID,
		&before.AvatarURL,
		&before.BackgroundMediaAssetID,
		&before.BackgroundURL,
		&before.IsPrivate,
		&before.IsolationLevel,
		&before.PurposeHint,
		&before.Version,
		&status,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrNotFound
	}
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	if replayed, found, err := personaProposalReplay(
		ctx,
		tx,
		commandKey,
		commandDigest,
	); err != nil || found {
		return finishPersonaReplay(ctx, tx, replayed, found, err)
	}
	if status == "retired" {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrRetired
	}
	if before.Version != command.ExpectedPersonaVersion {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrVersionConflict
	}

	occurredAt := time.Now().UTC()
	after := command.Snapshot
	after.Version = before.Version + 1
	result, err := tx.Exec(ctx, `
UPDATE personas SET
  display_name=$2,
  bio=$3,
  avatar_media_asset_id=$4,
  avatar_url=$5,
  background_media_asset_id=$6,
  background_url=$7,
  is_private=$8,
  isolation_level=$9,
  purpose_hint=$10,
  version=$11,
  updated_at=$12
WHERE persona_id=$1 AND version=$13`,
		command.PersonaID,
		after.DisplayName,
		after.Bio,
		after.AvatarMediaAssetID,
		after.AvatarURL,
		after.BackgroundMediaAssetID,
		after.BackgroundURL,
		after.IsPrivate,
		after.IsolationLevel,
		after.PurposeHint,
		after.Version,
		occurredAt,
		before.Version,
	)
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	if result.RowsAffected() != 1 {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrVersionConflict
	}

	mutation := personaports.ProfileProposalMutationResult{
		Before: before, After: after, OccurredAt: occurredAt,
	}
	eventPayload, err := json.Marshal(struct {
		ProposalID string `json:"proposalId"`
		PersonaID  string `json:"personaId"`
		Version    int64  `json:"version"`
	}{
		ProposalID: command.ProposalID,
		PersonaID:  command.PersonaID,
		Version:    mutation.After.Version,
	})
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,'PersonaUpdated',$4,$5)`,
		stablePersonaPacketID("rollback-event", command.ProposalID),
		command.PersonaID,
		after.Version,
		eventPayload,
		occurredAt,
	); err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	resultJSON, err := json.Marshal(mutation)
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_command_receipts(
  receipt_id, aggregate_id, idempotency_key, command_digest, aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6)`,
		stablePersonaPacketID("rollback-receipt", command.ProposalID),
		command.PersonaID,
		commandKey,
		commandDigest,
		after.Version,
		resultJSON,
	); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return personaports.ProfileProposalMutationResult{}, personamodel.ErrIdempotencyConflict
		}
		return personaports.ProfileProposalMutationResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	return mutation, nil
}

type personaQueryRower interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func personaProposalReplay(
	ctx context.Context,
	querier personaQueryRower,
	commandKey string,
	digest string,
) (personaports.ProfileProposalMutationResult, bool, error) {
	var storedDigest string
	var resultJSON []byte
	err := querier.QueryRow(ctx, `
SELECT command_digest, result_json
FROM personas_command_receipts
WHERE idempotency_key=$1`, commandKey).Scan(&storedDigest, &resultJSON)
	if errors.Is(err, pgx.ErrNoRows) {
		return personaports.ProfileProposalMutationResult{}, false, nil
	}
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, false, err
	}
	if storedDigest != digest {
		return personaports.ProfileProposalMutationResult{}, false, personamodel.ErrIdempotencyConflict
	}
	var result personaports.ProfileProposalMutationResult
	if err := json.Unmarshal(resultJSON, &result); err != nil {
		return personaports.ProfileProposalMutationResult{}, false, err
	}
	return result, true, nil
}

func finishPersonaReplay(
	ctx context.Context,
	tx pgx.Tx,
	result personaports.ProfileProposalMutationResult,
	found bool,
	err error,
) (personaports.ProfileProposalMutationResult, error) {
	if err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	if !found {
		return personaports.ProfileProposalMutationResult{},
			errors.New("Persona proposal replay result was not found")
	}
	if err := tx.Commit(ctx); err != nil {
		return personaports.ProfileProposalMutationResult{}, err
	}
	return result, nil
}

func personaProposalCommandKey(proposalID, action string) string {
	return "profile-proposal:" + strings.TrimSpace(proposalID) + ":" + action
}

func stablePersonaPacketID(kind, proposalID string) string {
	digest := sha256.Sum256([]byte(kind + "\x00" + proposalID))
	return fmt.Sprintf("persona-%s-%x", kind, digest[:16])
}

func applyProfileChangeSet(
	before personamodel.ProfileSnapshot,
	changes personamodel.ProfileChangeSet,
) personamodel.ProfileSnapshot {
	after := before
	if changes.DisplayName != nil {
		after.DisplayName = strings.TrimSpace(*changes.DisplayName)
	}
	if changes.Bio != nil {
		after.Bio = strings.TrimSpace(*changes.Bio)
	}
	if changes.AvatarMediaAssetID != nil {
		after.AvatarMediaAssetID = strings.TrimSpace(*changes.AvatarMediaAssetID)
		after.AvatarURL = ""
	}
	if changes.BackgroundMediaAssetID != nil {
		after.BackgroundMediaAssetID = strings.TrimSpace(*changes.BackgroundMediaAssetID)
		after.BackgroundURL = ""
	}
	if changes.IsPrivate != nil {
		after.IsPrivate = *changes.IsPrivate
	}
	if changes.IsolationLevel != nil {
		after.IsolationLevel = strings.TrimSpace(*changes.IsolationLevel)
	}
	if changes.PurposeHint != nil {
		after.PurposeHint = strings.TrimSpace(*changes.PurposeHint)
	}
	return after
}

func stringValue(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}

func boolValue(value *bool) bool {
	return value != nil && *value
}

var _ personaports.ProfileProposalStore = (*ProfileProposalPostgresStore)(nil)
var _ personaports.ProfileProposalVersionReader = (*ProfileProposalPostgresStore)(nil)
