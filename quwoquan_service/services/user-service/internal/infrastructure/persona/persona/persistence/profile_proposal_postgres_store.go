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

	personamodel "quwoquan_service/services/user-service/internal/domain/persona/model"
	personaports "quwoquan_service/services/user-service/internal/domain/persona/persona/ports"
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
WHERE sub_account_id=$1`, strings.TrimSpace(personaID)).Scan(&version, &status)
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
) error {
	commandDigest = strings.TrimSpace(commandDigest)
	if commandDigest == "" {
		return errors.New("Persona command digest is required")
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if replayed, err := personaProposalReplay(ctx, tx, command.ProposalID, commandDigest); err != nil || replayed {
		return finishPersonaReplay(ctx, tx, replayed, err)
	}

	var (
		currentVersion int64
		status         string
	)
	err = tx.QueryRow(ctx, `
SELECT version, status
FROM personas
WHERE sub_account_id=$1
FOR UPDATE`, command.PersonaID).Scan(&currentVersion, &status)
	if errors.Is(err, pgx.ErrNoRows) {
		return personamodel.ErrNotFound
	}
	if err != nil {
		return err
	}
	// The row lock may have waited behind a transaction that committed the same
	// proposal receipt. Re-read after locking before evaluating the version.
	if replayed, err := personaProposalReplay(ctx, tx, command.ProposalID, commandDigest); err != nil || replayed {
		return finishPersonaReplay(ctx, tx, replayed, err)
	}
	if status == "retired" {
		return personamodel.ErrRetired
	}
	if currentVersion != command.ExpectedPersonaVersion {
		return personamodel.ErrVersionConflict
	}

	changes := command.Changes
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
WHERE sub_account_id=$1 AND version=$18`,
		command.PersonaID,
		currentVersion+1,
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
		time.Now().UTC(),
		currentVersion,
	)
	if err != nil {
		return err
	}
	if result.RowsAffected() != 1 {
		return personamodel.ErrVersionConflict
	}

	eventPayload, err := json.Marshal(struct {
		ProposalID string                        `json:"proposalId"`
		PersonaID  string                        `json:"personaId"`
		Version    int64                         `json:"version"`
		Changes    personamodel.ProfileChangeSet `json:"changes"`
		AppliedAt  time.Time                     `json:"appliedAt"`
	}{
		ProposalID: command.ProposalID,
		PersonaID:  command.PersonaID,
		Version:    currentVersion + 1,
		Changes:    changes,
		AppliedAt:  time.Now().UTC(),
	})
	if err != nil {
		return err
	}
	eventID := stablePersonaPacketID("event", command.ProposalID)
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,'PersonaProfileProposalApplied',$4,NOW())`,
		eventID, command.PersonaID, currentVersion+1, eventPayload,
	); err != nil {
		return err
	}
	resultJSON, err := json.Marshal(struct {
		PersonaID string `json:"personaId"`
		Version   int64  `json:"version"`
	}{PersonaID: command.PersonaID, Version: currentVersion + 1})
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_command_receipts(
  receipt_id, aggregate_id, idempotency_key, command_digest, aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6)`,
		stablePersonaPacketID("receipt", command.ProposalID),
		command.PersonaID,
		command.ProposalID,
		commandDigest,
		currentVersion+1,
		resultJSON,
	); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return personamodel.ErrIdempotencyConflict
		}
		return err
	}
	return tx.Commit(ctx)
}

type personaQueryRower interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func personaProposalReplay(
	ctx context.Context,
	querier personaQueryRower,
	proposalID string,
	digest string,
) (bool, error) {
	var storedDigest string
	err := querier.QueryRow(ctx, `
SELECT command_digest
FROM personas_command_receipts
WHERE idempotency_key=$1`, proposalID).Scan(&storedDigest)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if storedDigest != digest {
		return false, personamodel.ErrIdempotencyConflict
	}
	return true, nil
}

func finishPersonaReplay(ctx context.Context, tx pgx.Tx, replayed bool, err error) error {
	if err != nil {
		return err
	}
	if !replayed {
		return nil
	}
	return tx.Commit(ctx)
}

func stablePersonaPacketID(kind, proposalID string) string {
	digest := sha256.Sum256([]byte(kind + "\x00" + proposalID))
	return fmt.Sprintf("persona-%s-%x", kind, digest[:16])
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
